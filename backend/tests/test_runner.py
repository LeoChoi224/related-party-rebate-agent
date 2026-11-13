"""그래프 실행기 · 체크포인터 테스트.

실제 그래프는 17 에서 생기므로, interrupt 하나만 있는 시험용 그래프를 쓴다.
"""

from typing import TypedDict

import pytest
from fastapi.testclient import TestClient
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents.checkpointer import make_checkpointer
from app.agents.runner import (
    InvalidRunStateError,
    pending_interrupts,
    resume_run,
    start_run,
    thread_config,
)
from app.core.database import make_engine
from app.main import create_app


class ToyState(TypedDict, total=False):
    amount: int
    decision: str


def ask_human(state: ToyState) -> ToyState:
    """금액을 보여 주고 사람 결정을 기다린다."""
    return {"decision": interrupt({"amount": state["amount"]})}


def build_toy(name: str, checkpointer):
    builder = StateGraph(ToyState)
    builder.add_node("ask_human", ask_human)
    builder.add_edge(START, "ask_human")
    builder.add_edge("ask_human", END)
    return builder.compile(checkpointer=checkpointer, name=name)


@pytest.fixture
def checkpointer():
    return make_checkpointer()


@pytest.fixture
def graph(checkpointer):
    return build_toy("claim_review", checkpointer)


def test_thread_id_is_graph_name_and_claim(graph):
    assert thread_config(graph, "RB-00054") == {
        "configurable": {"thread_id": "claim_review:RB-00054"}
    }


def test_start_stops_at_interrupt_then_resume_finishes(graph):
    """시작 → interrupt 에서 멈춤(대기 값 보임) → 재개 → 끝(대기 없음)."""
    result = start_run(graph, "RB-00054", {"amount": 3_888_097})
    assert "__interrupt__" in result
    assert pending_interrupts(graph, "RB-00054") == [{"amount": 3_888_097}]

    result = resume_run(graph, "RB-00054", "승인")
    assert result == {"amount": 3_888_097, "decision": "승인"}
    assert pending_interrupts(graph, "RB-00054") == []


def test_never_started_thread_has_nothing_pending(graph):
    assert pending_interrupts(graph, "RB-00006") == []


def test_resume_without_waiting_is_error(graph):
    """시작한 적 없는 스레드 · 이미 끝난 스레드는 재개할 수 없다."""
    with pytest.raises(InvalidRunStateError, match="기다리는 결정이 없습니다"):
        resume_run(graph, "RB-00006", "승인")

    start_run(graph, "RB-00054", {"amount": 1})
    resume_run(graph, "RB-00054", "승인")
    with pytest.raises(InvalidRunStateError, match="RB-00054"):
        resume_run(graph, "RB-00054", "반려")


def test_start_while_waiting_is_error(graph):
    """기다리는 결정이 있으면 다시 시작해 덮어쓰지 못한다."""
    start_run(graph, "RB-00054", {"amount": 1})
    with pytest.raises(InvalidRunStateError, match="이미 사람 결정을 기다리고"):
        start_run(graph, "RB-00054", {"amount": 2})
    assert pending_interrupts(graph, "RB-00054") == [{"amount": 1}]


def test_threads_do_not_mix_across_claims_and_graphs(graph, checkpointer):
    """같은 체크포인터를 써도 건 · 그래프가 다르면 따로 기다린다."""
    other_graph = build_toy("explanation_review", checkpointer)
    start_run(graph, "RB-00054", {"amount": 1})
    start_run(graph, "RB-00120", {"amount": 2})
    start_run(other_graph, "RB-00054", {"amount": 3})

    resume_run(graph, "RB-00054", "승인")
    assert pending_interrupts(graph, "RB-00054") == []
    assert pending_interrupts(graph, "RB-00120") == [{"amount": 2}]
    assert pending_interrupts(other_graph, "RB-00054") == [{"amount": 3}]


@pytest.fixture
def api_engine(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    yield eng
    eng.dispose()


def test_demo_reset_replaces_checkpointer(tmp_path, api_engine):
    """시연 초기화 뒤에는 옛 건의 대기가 남지 않는다(새 체크포인터)."""
    app = create_app(tmp_path / "missing", engine=api_engine)
    with TestClient(app) as client:
        old = app.state.checkpointer
        graph = build_toy("claim_review", old)
        start_run(graph, "RB-00054", {"amount": 1})

        assert client.post("/api/demo/reset").is_success

        new = app.state.checkpointer
        assert new is not old
        assert pending_interrupts(build_toy("claim_review", new), "RB-00054") == []
