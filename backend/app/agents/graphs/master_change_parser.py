"""master_change_parser 그래프(19): 정정 신고 문장 해석.

load_context → parse(AI: 문장 → 대리점 · 속성 · 새 값 · 정정일) → verify(가드: 있는 대리점인가 ·
문장에 그 대리점과 새 값이 실제로 있는가 · 지금 값과 다른가)
→ (문제면 1회 다시 parse / 2회 실패나 모델 없음이면 fallback) → save_parse → human_decision(interrupt).

- 대상은 신고 문장 한 건(master_change_report). thread_id 는 master_change_parser:master_change_report:{id}.
- 정정 적용은 이 그래프가 하지 않는다. 확인 API 가 서비스(services/master_change_report.py)로 사람이
  확인 · 수정한 값으로 20 의 정정을 적용한 뒤에 재개한다(17 · 18 과 같은 이유: 재개 값은 받는 순간 저장된다).
  그래서 그래프에 apply 노드가 없다(뼈대 docstring 의 apply_change 와 다름). 영향 건의 AI 검토는 건 상세에서 다시 누른다.
- 노드는 commit 하지 않는다. 요청 의존성이 해석 기록과 함께 확정한다.
"""

import logging

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.graphs.claim_review import ReviewContext
from app.agents.guards import check_master_change_parse
from app.agents.prompts import master_change_parse_messages
from app.agents.runner import pending_interrupts, resume_run, start_run
from app.agents.state import MasterChangeParserState
from app.models import Agency, IdentityAttribute, MasterChangeReport
from app.schemas.master_change import CORRECTABLE, MasterChangeParse

logger = logging.getLogger(__name__)

GRAPH_NAME = "master_change_parser"
TARGET_REPORT = "master_change_report"
# 첫 답 + 다시 생성 1회(claim_review 와 같음).
MAX_ATTEMPTS = 2


def _key(agency_id: str, attr_type: str) -> str:
    # 체크포인트에 저장되는 상태라 튜플 대신 문자열 키를 쓴다.
    return f"{agency_id}|{attr_type}"


def load_context(
    state: MasterChangeParserState, runtime: Runtime[ReviewContext]
) -> MasterChangeParserState:
    session = runtime.context.session
    agencies = session.execute(select(Agency.agency_id, Agency.agency_name)).all()
    current = session.execute(
        select(
            IdentityAttribute.agency_id,
            IdentityAttribute.attr_type,
            IdentityAttribute.value,
        ).where(
            IdentityAttribute.valid_to.is_(None),
            IdentityAttribute.attr_type.in_(list(CORRECTABLE)),
        )
    ).all()
    return {
        "agency_names": dict(agencies),
        "current_values": {_key(a, t): v for a, t, v in current},
        "llm_available": runtime.context.model is not None,
        "attempts": 0,
        "problems": [],
    }


def parse(
    state: MasterChangeParserState, runtime: Runtime[ReviewContext]
) -> MasterChangeParserState:
    attempts = state["attempts"] + 1
    model = runtime.context.model
    if model is None:
        return {"attempts": attempts, "parse": None}
    facts = {
        "신고_문장": state["raw_text"],
        "대리점_목록": [
            {"ID": agency_id, "이름": name}
            for agency_id, name in sorted(state["agency_names"].items())
        ],
    }
    try:
        result = model.with_structured_output(MasterChangeParse).invoke(
            master_change_parse_messages(facts, state["problems"])
        )
    # 네트워크 · 시간 초과 · 형식 오류 등 무엇이든 실패 1회로 친다(2회면 대체 모드).
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "master_change_parser LLM call failed (attempt %d): %s", attempts, e
        )
        return {"attempts": attempts, "parse": None, "problems": ["AI 호출 실패"]}
    return {"attempts": attempts, "parse": result.model_dump(mode="json")}


def verify(state: MasterChangeParserState) -> MasterChangeParserState:
    if state["parse"] is None:
        return {}
    current = {
        tuple(key.split("|", 1)): value
        for key, value in state["current_values"].items()
    }
    result = check_master_change_parse(
        MasterChangeParse.model_validate(state["parse"]),
        raw_text=state["raw_text"],
        agency_names=state["agency_names"],
        current_values=current,
    )
    if result.problems:
        logger.info(
            "정정 신고 해석이 가드에 걸렸습니다: %s", " · ".join(result.problems)
        )
    return {"problems": result.problems}


def route_after_verify(state: MasterChangeParserState) -> str:
    if not state["llm_available"]:
        return "fallback"
    if state["parse"] is None or state["problems"]:
        return "parse" if state["attempts"] < MAX_ATTEMPTS else "fallback"
    return "save_parse"


def fallback(state: MasterChangeParserState) -> MasterChangeParserState:
    logger.info("정정 신고를 AI 해석 없이 사람이 직접 입력하게 둡니다(대체 모드)")
    problems = state.get("problems") or []
    if not state["llm_available"]:
        problems = ["LLM 키가 없어 대체 모드"]
    return {"parse": None, "fallback_used": True, "problems": problems}


def save_parse(
    state: MasterChangeParserState, runtime: Runtime[ReviewContext]
) -> MasterChangeParserState:
    """확인 전에 화면이 해석을 보이도록 interrupt 앞에서 신고 행에 적는다."""
    report = runtime.context.session.get(MasterChangeReport, state["report_id"])
    p = state["parse"]
    parsed = MasterChangeParse.model_validate(p) if p else None
    report.ai_agency_id = parsed.agency_id if parsed else None
    report.ai_attr_type = parsed.attr_type if parsed else None
    report.ai_new_value = parsed.new_value.strip() if parsed else None
    report.ai_effective_date = parsed.effective_date if parsed else None
    report.ai_confidence = parsed.confidence if parsed else None
    report.problems = state.get("problems") or []
    report.verified = parsed is not None
    report.fallback_used = state.get("fallback_used", False)
    report.model = (
        getattr(runtime.context.model, "model_name", None) if parsed else None
    )
    runtime.context.session.flush()
    return {}


def human_decision(state: MasterChangeParserState) -> MasterChangeParserState:
    decision = interrupt({"report_id": state["report_id"]})
    return {"decision": decision}


def build_master_change_parser(checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    builder = StateGraph(MasterChangeParserState, context_schema=ReviewContext)
    for node in (load_context, parse, verify, fallback, save_parse, human_decision):
        builder.add_node(node)
    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "parse")
    builder.add_edge("parse", "verify")
    builder.add_conditional_edges(
        "verify", route_after_verify, ["parse", "fallback", "save_parse"]
    )
    builder.add_edge("fallback", "save_parse")
    builder.add_edge("save_parse", "human_decision")
    builder.add_edge("human_decision", END)
    return builder.compile(checkpointer=checkpointer, name=GRAPH_NAME)


def start_parse(
    session: Session,
    checkpointer: BaseCheckpointSaver,
    model: BaseChatModel | None,
    report: MasterChangeReport,
) -> None:
    """신고 문장을 해석해 사람 확인 앞(interrupt)까지 돌린다. 결과는 신고 행에 적혀 있다."""
    graph = build_master_change_parser(checkpointer)
    start_run(
        graph,
        f"{TARGET_REPORT}:{report.report_id}",
        {"report_id": report.report_id, "raw_text": report.raw_text},
        context=ReviewContext(session=session, model=model),
    )


def record_human_confirmation(
    session: Session,
    checkpointer: BaseCheckpointSaver,
    report_id: int,
    *,
    apply: bool,
    actor: str,
) -> bool:
    """서비스가 확인을 기록한 뒤 기다리는 해석을 끝낸다. 기다리는 해석이 없으면 False."""
    graph = build_master_change_parser(checkpointer)
    key = f"{TARGET_REPORT}:{report_id}"
    if not pending_interrupts(graph, key):
        return False
    resume_run(
        graph,
        key,
        {"apply": apply, "actor": actor},
        context=ReviewContext(session=session),
    )
    return True
