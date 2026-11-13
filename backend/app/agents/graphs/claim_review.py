"""claim_review 그래프: 장려금 건 검토.

load_context → compute_rules(코드) → assess(AI 추천) → verify(가드)
→ (숫자 · 형식이 틀리면 1회 다시 assess / 2회 실패나 모델 없음이면 fallback / 결재 단계가 낮으면 raise_authority)
→ save_recommendation → human_decision(interrupt) → record_decision.

- 검토 단위는 전결 건 하나 또는 승인 요청 하나다(services/claim_detail.review_unit).
- 건 상태는 이 그래프가 바꾸지 않는다. 결정 API 가 09 서비스로 권한 · 상태를 검사하고 바꾼 뒤,
  통과했을 때만 재개한다. 재개 값은 받는 순간 저장되어, 노드 안에서 403 · 409 가 나면
  다음 재개가 그 틀린 결정으로 돌기 때문이다. record_decision 은 추천 행에 결정 · 일치만 적는다.
- 노드는 commit 하지 않는다. 요청 의존성이 상태 변경과 추천 기록을 한 트랜잭션으로 확정한다.
- 그래프는 요청마다 app.state.checkpointer 로 compile 한다(시연 초기화가 체크포인터를 바꾼다).
"""

import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agents.guards import check_assessment
from app.agents.prompts import claim_review_messages
from app.agents.runner import (
    InvalidRunStateError,
    pending_interrupts,
    resume_run,
    start_run,
)
from app.agents.state import ClaimReviewState
from app.models import AIRecommendation, RebateClaim
from app.models.enums import ClaimStatus, Decision
from app.schemas.ai_recommendation import ClaimAssessment
from app.schemas.rebate import ClaimDetail
from app.services.ai_agreement import recommendation_matches
from app.services.approval_authority import required_authority
from app.services.claim_detail import get_claim_detail, review_unit

logger = logging.getLogger(__name__)

GRAPH_NAME = "claim_review"
# 첫 답 + 다시 생성 1회. 2회 실패하면 대체 모드(설계안 4장).
MAX_ATTEMPTS = 2
# 사람 결정을 기다리는 상태. 그 밖의 건은 검토할 결정이 없다.
REVIEWABLE = {ClaimStatus.AWAITING_SUPPORT, ClaimStatus.AWAITING_EXECUTIVE}


@dataclass
class ReviewContext:
    """노드가 쓰는 요청별 자원. 상태가 아니라 체크포인트에 저장되지 않는다."""

    session: Session
    model: BaseChatModel | None = None


def _facts(detail: ClaimDetail) -> dict[str, Any]:
    """프롬프트에 넣을 사실. 화면 응답에서 판단에 필요한 것만 추린다."""
    return {
        "건": {
            "건_ID": detail.rebate_id,
            "대리점": f"{detail.agency_id} {detail.agency_name}",
            "대상월": detail.period_ym,
            "장려금액_krw": detail.rebate_amount_krw,
            "근거_행": f"{detail.source_file}:{detail.source_row}",
        },
        "판정_단위": {
            "관련자_그룹": detail.group_label or "없음(단독 대리점)",
            "구성_건": [
                {
                    "건_ID": c.rebate_id,
                    "대리점": f"{c.agency_id} {c.agency_name}",
                    "장려금액_krw": c.rebate_amount_krw,
                }
                for c in detail.unit_claims
            ],
            "합산_krw": detail.group_sum_krw,
        },
        "규정": {
            "한도_krw": detail.limit_krw,
            "코드가_계산한_최소_결재권자": detail.min_authority,
        },
        "관련자_근거": [
            {
                "대리점_쌍": [e.agency_a, e.agency_b],
                "판정": e.judgement,
                "일치_속성": [
                    {"속성": m.attr, "값": m.value, "근거_행": m.refs_a + m.refs_b}
                    for m in e.matched_attrs
                ],
            }
            for e in detail.evidence
        ],
    }


def load_context(
    state: ClaimReviewState, runtime: Runtime[ReviewContext]
) -> ClaimReviewState:
    detail = get_claim_detail(runtime.context.session, state["rebate_id"])
    return {
        "facts": _facts(detail),
        "group_sum_krw": detail.group_sum_krw,
        "min_authority": detail.min_authority,
        "llm_available": runtime.context.model is not None,
        "attempts": 0,
        "problems": [],
    }


def compute_rules(state: ClaimReviewState) -> ClaimReviewState:
    """최소 결재권자를 코드로 다시 계산해 접수 때 값과 맞춰 본다. AI 는 이 값을 바꿀 수 없다."""
    required = required_authority(state["group_sum_krw"])
    if required != state["min_authority"]:
        # 같은 합산에서 결재권자가 달라졌다면 데이터나 코드의 버그다. 숨기지 않고 멈춘다.
        raise RuntimeError(
            f"최소 결재권자 불일치: 저장 {state['min_authority']} · 계산 {required}"
        )
    return {}


def assess(
    state: ClaimReviewState, runtime: Runtime[ReviewContext]
) -> ClaimReviewState:
    attempts = state["attempts"] + 1
    model = runtime.context.model
    if model is None:
        return {"attempts": attempts, "assessment": None}
    messages = claim_review_messages(state["facts"], state["problems"])
    try:
        result = model.with_structured_output(ClaimAssessment).invoke(messages)
    # 네트워크 · 시간 초과 · 형식 오류 등 무엇이든 실패 1회로 친다(2회면 대체 모드).
    except Exception as e:  # noqa: BLE001
        logger.warning("claim_review LLM call failed (attempt %d): %s", attempts, e)
        return {"attempts": attempts, "assessment": None, "problems": ["AI 호출 실패"]}
    return {"attempts": attempts, "assessment": result.model_dump(mode="json")}


def verify(state: ClaimReviewState) -> ClaimReviewState:
    if state["assessment"] is None:
        return {}
    result = check_assessment(
        ClaimAssessment.model_validate(state["assessment"]),
        group_sum_krw=state["group_sum_krw"],
        min_authority=state["min_authority"],
    )
    if result.problems:
        logger.info("AI 평가가 가드에 걸렸습니다: %s", " · ".join(result.problems))
    return {"problems": result.problems, "authority_raised": result.authority_raised}


def route_after_verify(state: ClaimReviewState) -> str:
    if not state["llm_available"]:
        return "fallback"
    if state["assessment"] is None or state["problems"]:
        return "assess" if state["attempts"] < MAX_ATTEMPTS else "fallback"
    if state["authority_raised"]:
        return "raise_authority"
    return "save_recommendation"


def raise_authority(state: ClaimReviewState) -> ClaimReviewState:
    """결재권자는 코드 값(min_authority)으로 고정된다. AI 값은 불일치 기록용으로 남긴다."""
    logger.info(
        "AI 결재권자 %s 를 코드 값 %s 로 올렸습니다",
        state["assessment"]["ai_authority"],
        state["min_authority"],
    )
    return {"authority_raised": True}


def fallback(state: ClaimReviewState) -> ClaimReviewState:
    logger.info("AI 추천 없이 규정 결과만 남깁니다(대체 모드)")
    return {"assessment": None, "fallback_used": True, "authority_raised": False}


def save_recommendation(
    state: ClaimReviewState, config: RunnableConfig, runtime: Runtime[ReviewContext]
) -> ClaimReviewState:
    """결정 전에 화면 패널이 보이도록 interrupt 앞에서 추천 행을 저장한다."""
    a = state["assessment"]
    model = runtime.context.model
    rec = AIRecommendation(
        graph=GRAPH_NAME,
        thread_id=config["configurable"]["thread_id"],
        target_type=state["target_type"],
        target_id=state["target_id"],
        recommendation=a["recommendation"] if a else None,
        rationale=a["rationale"] if a else [],
        counter_evidence=a["counter_evidence"] if a else [],
        confidence=a["confidence"] if a else None,
        min_authority=state["min_authority"],
        ai_authority=a["ai_authority"] if a else None,
        authority_raised=state.get("authority_raised", False),
        verified=a is not None,
        fallback_used=state.get("fallback_used", False),
        model=getattr(model, "model_name", None) if a else None,
    )
    runtime.context.session.add(rec)
    runtime.context.session.flush()
    return {"rec_id": rec.rec_id}


def human_decision(state: ClaimReviewState) -> ClaimReviewState:
    decision = interrupt({"rec_id": state["rec_id"]})
    return {"decision": decision}


def record_decision(
    state: ClaimReviewState, runtime: Runtime[ReviewContext]
) -> ClaimReviewState:
    """사람 결정과 추천 일치 여부를 적는다. 건 상태는 결정 API 가 이미 바꿨다."""
    rec = runtime.context.session.get(AIRecommendation, state["rec_id"])
    d = state["decision"]
    rec.human_decision = d["decision"]
    rec.human_reason = d["reason"].strip() or None
    rec.decided_by = d["actor"]
    rec.decided_at = func.now()
    # "소명 먼저"는 반려하면서 소명을 요청한 결정과 같다(21 · 25).
    rec.agreed = (
        None
        if rec.recommendation is None
        else recommendation_matches(
            rec.recommendation, d["decision"], explained=d.get("explained", False)
        )
    )
    runtime.context.session.flush()
    return {}


def build_claim_review(checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    builder = StateGraph(ClaimReviewState, context_schema=ReviewContext)
    for node in (
        load_context,
        compute_rules,
        assess,
        verify,
        raise_authority,
        fallback,
        save_recommendation,
        human_decision,
        record_decision,
    ):
        builder.add_node(node)
    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "compute_rules")
    builder.add_edge("compute_rules", "assess")
    builder.add_edge("assess", "verify")
    builder.add_conditional_edges(
        "verify",
        route_after_verify,
        ["assess", "fallback", "raise_authority", "save_recommendation"],
    )
    builder.add_edge("raise_authority", "save_recommendation")
    builder.add_edge("fallback", "save_recommendation")
    builder.add_edge("save_recommendation", "human_decision")
    builder.add_edge("human_decision", "record_decision")
    builder.add_edge("record_decision", END)
    return builder.compile(checkpointer=checkpointer, name=GRAPH_NAME)


def review_target(session: Session, rebate_id: str) -> tuple[str, str]:
    """AI 검토를 시작할 수 있는 건이면 그 검토 단위. 없는 건 LookupError, 결정 대기가 아니면 409."""
    claim = session.get(RebateClaim, rebate_id)
    if claim is None:
        raise LookupError(f"장려금 건 {rebate_id} 이(가) 없습니다")
    if claim.status not in REVIEWABLE:
        raise InvalidRunStateError(
            f"결정을 기다리는 건(전결대기 · 상신대기)만 AI 검토할 수 있습니다: "
            f"{claim.status} ({rebate_id})"
        )
    return review_unit(session, rebate_id)


def start_claim_review(
    session: Session,
    checkpointer: BaseCheckpointSaver,
    model: BaseChatModel | None,
    rebate_id: str,
) -> AIRecommendation:
    """검토를 사람 결정 앞(interrupt)까지 돌리고 저장한 추천 행을 돌려준다."""
    target_type, target_id = review_target(session, rebate_id)
    graph = build_claim_review(checkpointer)
    key = f"{target_type}:{target_id}"
    start_run(
        graph,
        key,
        {"rebate_id": rebate_id, "target_type": target_type, "target_id": target_id},
        context=ReviewContext(session=session, model=model),
    )
    rec_id = pending_interrupts(graph, key)[0]["rec_id"]
    return session.get(AIRecommendation, rec_id)


def record_human_decision(
    session: Session,
    checkpointer: BaseCheckpointSaver,
    target_type: str,
    target_id: str,
    *,
    decision: Decision,
    reason: str,
    actor: str,
    explained: bool = False,
) -> bool:
    """검사를 통과한 결정을 기다리는 검토에 넣는다. 검토가 없으면 아무것도 안 하고 False.

    explained 는 반려와 함께 소명을 요청했는지다("소명 먼저" 추천과의 일치 판단에 쓴다).
    """
    graph = build_claim_review(checkpointer)
    key = f"{target_type}:{target_id}"
    if not pending_interrupts(graph, key):
        return False
    resume_run(
        graph,
        key,
        {
            "decision": str(decision),
            "reason": reason,
            "actor": actor,
            "explained": explained,
        },
        context=ReviewContext(session=session),
    )
    return True
