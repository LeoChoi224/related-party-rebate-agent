"""LangGraph 체크포인터 생성.

그래프 진행 위치(어느 interrupt 에서 멈췄는지)만 저장한다. 업무 상태의 기준은 업무 DB 다.
메모리에만 있어 앱 재시작 · 시연 초기화 때 사라지는 것이 의도다(업무 DB 도 그때 원본으로 돌아간다).
사라진 뒤에는 업무 DB 의 현재 상태에서 그래프를 다시 시작한다(17).
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver


def make_checkpointer() -> BaseCheckpointSaver:
    """새 체크포인터. 파일 저장으로 바꿀 때는 이 함수만 고친다."""
    return InMemorySaver()
