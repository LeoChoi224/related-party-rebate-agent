"""explanation_review 그래프: 소명 회신 검토.

load_context → extract_claims(AI, 회신 속 주장) → check_claim(주장마다 도구로 조회 · 대조, 반복)
→ assess(AI, 증빙 충분 · 부족) → verify(가드)
→ (종합 판단이 틀리면 1회 다시 assess / 2회 실패나 모델 없음이면 fallback)
→ save_review → human_decision(interrupt) → 끝.

- 건 상태와 사람 확인 결과는 이 그래프가 적지 않는다. 확인 API 가 서비스(services/explanation.py)로
  권한 · 상태를 검사하고 상태를 바꾸며 확인 결과 컬럼까지 쓴 뒤, 통과했을 때만 재개한다.
  재개 값은 받는 순간 저장되어, 노드 안에서 403 · 409 가 나면 다음 재개가 그 틀린 결정으로 돌기 때문이다(17).
  AI 검토 없이 사람이 바로 확인하는 길에서도 기록이 빠지지 않는 이유이기도 하다.
- check_claim 은 노드 하나가 주장 하나를 처리하고, 남은 주장이 있으면 자기 자신으로 돌아온다.
  안에서 모델이 도구를 골라 부르는 반복을 직접 돌린다(조회 상한 MAX_TOOL_STEPS).
- 주장 판정의 근거는 도구가 실제로 돌려준 행만 인정한다(가드). 근거 없는 일치 · 불일치는 확인불가로 내린다.
- 노드는 commit 하지 않는다. 요청 의존성이 상태 변경과 기록을 한 트랜잭션으로 확정한다.
- 그래프는 요청마다 app.state.checkpointer 로 compile 한다(시연 초기화가 체크포인터를 바꾼다).
"""

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt
from sqlalchemy.orm import Session

from app.agents.graphs.claim_review import ReviewContext
from app.agents.guards import check_claim_result, check_explanation_assessment
from app.agents.prompts import (
    EXPLANATION_CHECK_FINAL,
    explanation_assess_messages,
    explanation_check_messages,
    explanation_extract_messages,
)
from app.agents.runner import (
    InvalidRunStateError,
    pending_interrupts,
    resume_run,
    start_run,
)
from app.agents.state import ExplanationReviewState
from app.agents.tools import build_tools, collect_refs
from app.models import (
    Agency,
    ExplanationCheck,
    ExplanationReply,
    ExplanationRequest,
    RebateClaim,
)
from app.models.enums import CheckVerdict, ExplanationJudgement, ExplanationStatus
from app.schemas.explanation import (
    CheckResult,
    ExplanationAssessment,
    ExtractedClaims,
)

logger = logging.getLogger(__name__)

GRAPH_NAME = "explanation_review"
# 종합 판단: 첫 답 + 다시 생성 1회. 2회 실패하면 대체 모드(설계안 4장).
MAX_ATTEMPTS = 2
# 주장 하나를 대조할 때 모델이 도구를 부를 수 있는 라운드 수.
MAX_TOOL_STEPS = 4


def load_context(
    state: ExplanationReviewState, runtime: Runtime[ReviewContext]
) -> ExplanationReviewState:
    session = runtime.context.session
    reply = session.get(ExplanationReply, state["reply_id"])
    request = session.get(ExplanationRequest, reply.exp_id)
    claim = session.get(RebateClaim, request.rebate_id)
    agency = session.get(Agency, claim.agency_id)
    return {
        "rebate_id": claim.rebate_id,
        "agency_id": claim.agency_id,
        "facts": {
            "대리점": f"{claim.agency_id} {agency.agency_name}",
            "요청_항목": request.requested_items,
            "회신_원문": reply.raw_text,
        },
        "llm_available": runtime.context.model is not None,
        "claims": [],
        "extract_failed": False,
        "cursor": 0,
        "checks": [],
        "attempts": 0,
        "assessment": None,
        "problems": [],
        "fallback_used": False,
    }


def extract_claims(
    state: ExplanationReviewState, runtime: Runtime[ReviewContext]
) -> ExplanationReviewState:
    model = runtime.context.model
    if model is None:
        return {"claims": []}
    try:
        result = model.with_structured_output(ExtractedClaims).invoke(
            explanation_extract_messages(state["facts"])
        )
    # 네트워크 · 시간 초과 · 형식 오류 등 무엇이든 실패로 친다(대체 모드로 간다).
    except Exception as e:  # noqa: BLE001
        logger.warning("explanation_review 주장 추출 실패: %s", e)
        return {"claims": [], "extract_failed": True}
    return {"claims": [c.strip() for c in result.claims if c.strip()]}


def route_after_extract(state: ExplanationReviewState) -> str:
    if not state["llm_available"] or state["extract_failed"]:
        return "fallback"
    return "check_claim" if state["claims"] else "assess"


def _run_tool(tools: dict[str, BaseTool], call: dict[str, Any]) -> dict[str, Any]:
    """모델이 요청한 도구 호출 하나를 실행한다. 이름 · 인자가 틀려도 예외 대신 오류를 돌려줘 모델이 고치게 한다."""
    tool = tools.get(call["name"])
    if tool is None:
        return {"error": f"없는 도구입니다: {call['name']}", "rows": []}
    try:
        return tool.invoke(call["args"])
    except Exception as e:  # noqa: BLE001
        return {"error": f"도구 실행 실패: {e}", "rows": []}


def _unverifiable(seq: int, claim_text: str, finding: str, used: list[str]) -> dict:
    return {
        "seq": seq,
        "claim_text": claim_text,
        "verdict": str(CheckVerdict.UNVERIFIABLE),
        "finding": finding,
        "tool_used": used,
        "evidence_ref": [],
    }


def check_claim(
    state: ExplanationReviewState, runtime: Runtime[ReviewContext]
) -> ExplanationReviewState:
    """주장 하나를 도구로 조회해 대조하고 cursor 를 올린다. 실패해도 그 주장만 확인불가로 두고 계속한다."""
    cursor = state["cursor"]
    claim_text = state["claims"][cursor]
    seq = cursor + 1
    model: BaseChatModel = runtime.context.model
    tools = build_tools(runtime.context.session)
    by_name = {tool.name: tool for tool in tools}
    messages: list[Any] = explanation_check_messages(claim_text, state["facts"])
    used: list[str] = []
    seen_refs: set[str] = set()

    try:
        llm = model.bind_tools(tools)
        for _ in range(MAX_TOOL_STEPS):
            reply = llm.invoke(messages)
            if not reply.tool_calls:
                break
            messages.append(reply)
            # 한 번에 여러 도구를 부를 수 있다. 호출마다 결과 메시지가 있어야 다음 호출이 받아들여진다.
            for call in reply.tool_calls:
                output = _run_tool(by_name, call)
                used.append(call["name"])
                seen_refs |= collect_refs(output)
                messages.append(
                    ToolMessage(
                        content=json.dumps(output, ensure_ascii=False, default=str),
                        tool_call_id=call["id"],
                    )
                )
        messages.append(("human", EXPLANATION_CHECK_FINAL))
        result = model.with_structured_output(CheckResult).invoke(messages)
    except Exception as e:  # noqa: BLE001
        logger.warning("explanation_review 주장 대조 실패 (%s): %s", claim_text, e)
        entry = _unverifiable(
            seq, claim_text, "AI 호출 실패로 대조하지 못했습니다", used
        )
    else:
        guarded = check_claim_result(result, seen_refs)
        if guarded.downgraded:
            logger.info("근거 행이 없어 확인불가로 내렸습니다: %s", claim_text)
        entry = {
            "seq": seq,
            "claim_text": claim_text,
            "verdict": str(guarded.verdict),
            "finding": (
                "도구 조회 결과에 없는 근거라 확인불가로 내렸습니다. " + result.finding
                if guarded.downgraded
                else result.finding
            ),
            "tool_used": list(dict.fromkeys(used)),
            "evidence_ref": guarded.evidence_refs,
        }
    # 리듀서가 없어 덮어쓰기라, 기존 목록에 한 건을 붙인 새 목록을 돌려준다.
    return {"checks": [*state["checks"], entry], "cursor": cursor + 1}


def route_after_check(state: ExplanationReviewState) -> str:
    return "check_claim" if state["cursor"] < len(state["claims"]) else "assess"


def assess(
    state: ExplanationReviewState, runtime: Runtime[ReviewContext]
) -> ExplanationReviewState:
    attempts = state["attempts"] + 1
    model = runtime.context.model
    if model is None:
        return {"attempts": attempts, "assessment": None}
    messages = explanation_assess_messages(
        state["facts"], state["checks"], state["problems"]
    )
    try:
        result = model.with_structured_output(ExplanationAssessment).invoke(messages)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "explanation_review LLM call failed (attempt %d): %s", attempts, e
        )
        return {"attempts": attempts, "assessment": None, "problems": ["AI 호출 실패"]}
    return {"attempts": attempts, "assessment": result.model_dump(mode="json")}


def verify(state: ExplanationReviewState) -> ExplanationReviewState:
    if state["assessment"] is None:
        return {}
    result = check_explanation_assessment(
        ExplanationAssessment.model_validate(state["assessment"]), state["checks"]
    )
    if result.problems:
        logger.info("AI 소명 판단이 가드에 걸렸습니다: %s", " · ".join(result.problems))
    return {"problems": result.problems}


def route_after_verify(state: ExplanationReviewState) -> str:
    if not state["llm_available"]:
        return "fallback"
    if state["assessment"] is None or state["problems"]:
        return "assess" if state["attempts"] < MAX_ATTEMPTS else "fallback"
    return "save_review"


def fallback(state: ExplanationReviewState) -> ExplanationReviewState:
    logger.info("AI 판단 없이 회신 원문만 남깁니다(대체 모드)")
    return {"assessment": None, "fallback_used": True}


def save_review(
    state: ExplanationReviewState, runtime: Runtime[ReviewContext]
) -> ExplanationReviewState:
    """결정 전에 화면이 보이도록 interrupt 앞에서 AI 판단과 주장별 대조 결과를 저장한다."""
    session = runtime.context.session
    reply = session.get(ExplanationReply, state["reply_id"])
    a = state["assessment"]
    reply.ai_judgement = a["judgement"] if a else None
    reply.ai_rationale = a["rationale"] if a else []
    reply.missing_evidence = a["missing_evidence"] if a else []
    reply.follow_up_request = (a["follow_up_request"].strip() or None) if a else None
    reply.ai_confidence = a["confidence"] if a else None
    reply.verified = a is not None
    reply.fallback_used = state["fallback_used"]
    reply.model = getattr(runtime.context.model, "model_name", None) if a else None
    # 종합 판단이 대체 모드여도 그 전에 끝낸 주장별 대조 결과는 사람에게 도움이 되므로 남긴다.
    for c in state["checks"]:
        session.add(
            ExplanationCheck(
                reply_id=reply.reply_id,
                seq=c["seq"],
                claim_text=c["claim_text"],
                verdict=c["verdict"],
                finding=c["finding"],
                tool_used=c["tool_used"],
                evidence_ref=c["evidence_ref"],
            )
        )
    session.flush()
    return {}


def human_decision(state: ExplanationReviewState) -> ExplanationReviewState:
    decision = interrupt({"reply_id": state["reply_id"]})
    return {"decision": decision}


def build_explanation_review(checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    builder = StateGraph(ExplanationReviewState, context_schema=ReviewContext)
    for node in (
        load_context,
        extract_claims,
        check_claim,
        assess,
        verify,
        fallback,
        save_review,
        human_decision,
    ):
        builder.add_node(node)
    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "extract_claims")
    builder.add_conditional_edges(
        "extract_claims", route_after_extract, ["fallback", "check_claim", "assess"]
    )
    builder.add_conditional_edges(
        "check_claim", route_after_check, ["check_claim", "assess"]
    )
    builder.add_edge("assess", "verify")
    builder.add_conditional_edges(
        "verify", route_after_verify, ["assess", "fallback", "save_review"]
    )
    builder.add_edge("fallback", "save_review")
    builder.add_edge("save_review", "human_decision")
    builder.add_edge("human_decision", END)
    return builder.compile(checkpointer=checkpointer, name=GRAPH_NAME)


def _thread_key(reply_id: int) -> str:
    return f"explanation_reply:{reply_id}"


def reviewable_reply(session: Session, reply_id: int) -> ExplanationReply:
    """AI 검토를 시작할 수 있는 회신. 없으면 LookupError, 이미 확인했으면 409."""
    reply = session.get(ExplanationReply, reply_id)
    if reply is None:
        raise LookupError(f"소명 회신 {reply_id} 이(가) 없습니다")
    request = session.get(ExplanationRequest, reply.exp_id)
    if request.status != ExplanationStatus.REPLIED:
        raise InvalidRunStateError(
            f"확인 전 회신만 AI 검토할 수 있습니다: {request.status} (회신 {reply_id})"
        )
    return reply


def start_explanation_review(
    session: Session,
    checkpointer: BaseCheckpointSaver,
    model: BaseChatModel | None,
    reply_id: int,
) -> ExplanationReply:
    """검토를 사람 확인 앞(interrupt)까지 돌리고 갱신된 회신 행을 돌려준다."""
    reply = reviewable_reply(session, reply_id)
    graph = build_explanation_review(checkpointer)
    start_run(
        graph,
        _thread_key(reply_id),
        {"reply_id": reply_id},
        context=ReviewContext(session=session, model=model),
    )
    return reply


def record_human_confirmation(
    session: Session,
    checkpointer: BaseCheckpointSaver,
    reply_id: int,
    *,
    judgement: ExplanationJudgement,
    reason: str,
    actor: str,
) -> bool:
    """검사를 통과한 확인을 기다리는 검토에 넣어 끝낸다. 검토가 없으면 아무것도 안 하고 False."""
    graph = build_explanation_review(checkpointer)
    key = _thread_key(reply_id)
    if not pending_interrupts(graph, key):
        return False
    resume_run(
        graph,
        key,
        {"judgement": str(judgement), "reason": reason, "actor": actor},
        context=ReviewContext(session=session),
    )
    return True
