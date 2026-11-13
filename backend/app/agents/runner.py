"""그래프 실행기.

그래프를 대상 하나의 스레드로 시작하고, 사람 결정이나 외부 회신이 오면 interrupt 지점에서 재개한다.

- thread_id 는 "그래프이름:대상"(예: claim_review:approval_request:1). 체크포인터 하나를 그래프 셋이 같이 쓰므로,
  대상만 쓰면 한 건에 도는 claim_review 와 explanation_review 가 서로의 진행 위치를 덮는다.
  대상은 그래프가 정한다(claim_review 는 전결 건 하나 또는 승인 요청 하나).
- 그래프 이름은 compile(name=...) 으로 붙인 graph.name 을 쓴다.
- 그래프는 요청마다 app.state.checkpointer 로 compile 한다. 시연 초기화가 체크포인터를 새로 바꾸므로,
  앱 시작 때 한 번만 compile 하면 옛 체크포인터를 붙잡는다.
- 체크포인트가 없을 때 업무 DB 에서 어디부터 다시 시작할지는 그래프마다 정한다.
- context 는 노드가 쓰는 요청별 자원(DB 세션 · 모델)이다. 상태가 아니라서 체크포인트에 저장되지 않는다.
- 재개 값은 받는 순간 체크포인트에 저장되어, 재개 뒤 노드가 실패해도 다음 재개는 처음 값으로 돈다.
  그래서 권한 · 상태 검사를 통과한 값만 재개에 넣는다(17 결정 API).
"""

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command


class InvalidRunStateError(Exception):
    """기다리는 중인데 또 시작하거나, 기다리지 않는데 재개하려 함. API 는 409 로 돌려준다."""


def thread_config(graph: CompiledStateGraph, target_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": f"{graph.name}:{target_id}"}}


def pending_interrupts(graph: CompiledStateGraph, target_id: str) -> list[Any]:
    """멈춘 지점이 내놓은 값들. 비어 있으면 기다리는 것이 없다(시작한 적 없는 스레드 포함)."""
    state = graph.get_state(thread_config(graph, target_id))
    return [item.value for item in state.interrupts]


def start_run(
    graph: CompiledStateGraph,
    target_id: str,
    inputs: dict[str, Any],
    *,
    context: Any = None,
) -> dict[str, Any]:
    """그래프를 처음부터 돌린다. interrupt 에서 멈추면 결과에 "__interrupt__" 가 있다."""
    # 같은 스레드에 새 입력을 넣으면 기다리던 사람 결정이 버려진다.
    if pending_interrupts(graph, target_id):
        raise InvalidRunStateError(
            f"{graph.name} · {target_id} 는 이미 사람 결정을 기다리고 있습니다"
        )
    return graph.invoke(inputs, thread_config(graph, target_id), context=context)


def resume_run(
    graph: CompiledStateGraph, target_id: str, value: Any, *, context: Any = None
) -> dict[str, Any]:
    """멈춘 지점에 사람 결정(value)을 넣고 이어서 돌린다."""
    # 확인 없이 보내면 오류 없이 그래프가 입력 없이 처음부터 돌아 노드 안에서 엉뚱하게 깨진다.
    if not pending_interrupts(graph, target_id):
        raise InvalidRunStateError(
            f"{graph.name} · {target_id} 는 기다리는 결정이 없습니다"
        )
    return graph.invoke(
        Command(resume=value), thread_config(graph, target_id), context=context
    )
