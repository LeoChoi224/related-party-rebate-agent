"""부서별 작업 배정.

상태 전이가 일어나면 규칙표(TASK_RULES)로 부서 작업을 만든다. 상태를 바꾸는 길이
services/claim_state.py 의 transition 하나라서, 그 함수가 이 모듈을 부른다.
건이 어떤 상태를 떠나면 그 상태가 만든 열린 작업은 자동으로 완료한다.
상태 전이가 아닌 작업: 접수 때 정황 소명 요청(R3, 지급은 막지 않음), 상계 영업 의견 · 회수 약정 관리(23),
감사 사후 검토(24, services/retro_review.py).
사람이 손으로 닫을 수 있는 것은 이 작업들뿐이다. 전이 작업은 건을 처리하면 닫힌다.

claim_state 가 이 모듈을 import 하므로, 이 모듈은 claim_state 를 import 하지 않는다(순환 방지).
"""

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EventLog, GroupVersion, RebateClaim, RelationEdge, Task
from app.models.enums import ClaimStatus as S
from app.models.enums import Department, RelationJudgement, TaskStatus

# (이전 상태, 이후 상태) → (부서, 작업). 이전 상태가 None 이면 "아무거나".
TASK_RULES: dict[tuple[S | None, S], tuple[Department, str]] = {
    (None, S.APPROVED): (Department.FINANCE, "지급 실행"),
    (None, S.AWAITING_EXPLANATION): (Department.SALES_SUPPORT, "소명 요청"),
    # 지급보류는 들어오는 길이 둘이라 이전 상태로 부서가 갈린다.
    (S.AWAITING_EXPLANATION, S.ON_HOLD): (Department.SALES_SUPPORT, "추가 소명 요청"),
    (S.PAYMENT_ORDERED, S.ON_HOLD): (Department.FINANCE, "지급 계좌 확인"),
    (None, S.OFFSET_REVIEW): (Department.FINANCE, "상계 검토"),
    (None, S.NEEDS_REVIEW): (Department.SALES_SUPPORT, "재판정"),
}

TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.OPEN: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.DONE}),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.DONE}),
    TaskStatus.DONE: frozenset(),
}


class InvalidTaskTransitionError(Exception):
    """작업 상태 전이표에 없는 변경(API 409)."""


def find_rule(from_status: str, to_status: str) -> tuple[Department, str] | None:
    """정확한 (이전, 이후) 짝을 먼저 찾고, 없으면 이전 상태 '아무거나' 규칙을 쓴다."""
    return TASK_RULES.get((from_status, to_status)) or TASK_RULES.get((None, to_status))


def create_task(
    session: Session,
    *,
    dept: Department,
    task_type: str,
    ref_id: str,
    detail: str,
    trigger_status: str | None = None,
    event: EventLog | None = None,
) -> Task:
    """장려금 건에 작업 하나를 연다. 상태 전이가 아닌 작업은 trigger · event 를 비운다."""
    task = Task(
        dept=dept,
        task_type=task_type,
        ref_type="rebate_claim",
        ref_id=ref_id,
        status=TaskStatus.OPEN,
        trigger_status=trigger_status,
        detail=detail,
        created_by_event=event.event_id if event else None,
    )
    session.add(task)
    session.flush()
    return task


def on_claim_transition(
    session: Session, claim: RebateClaim, event: EventLog
) -> Task | None:
    """전이 직후 불린다. 떠나는 상태가 만든 작업을 닫고, 규칙이 있으면 새 작업을 연다."""
    # 닫기가 먼저다. 닫을 대상을 '떠나는 상태가 만든 작업'으로 좁혀, 같은 상태로
    # 다시 돌아와도(지급보류 → 소명대기 → 지급보류) 새 작업이 바로 닫히지 않는다.
    open_tasks = session.scalars(
        select(Task).where(
            Task.ref_type == "rebate_claim",
            Task.ref_id == claim.rebate_id,
            Task.trigger_status == event.from_status,
            Task.status != TaskStatus.DONE,
        )
    )
    for task in open_tasks:
        task.status = TaskStatus.DONE
        task.closed_at = func.now()

    rule = find_rule(event.from_status, event.to_status)
    if rule is None:
        return None
    dept, task_type = rule
    return create_task(
        session,
        dept=dept,
        task_type=task_type,
        ref_id=claim.rebate_id,
        detail=f"{event.from_status} → {event.to_status}: {event.reason}",
        trigger_status=event.to_status,
        event=event,
    )


def open_circumstantial_tasks(
    session: Session, claims: Iterable[RebateClaim]
) -> list[Task]:
    """정황 관계(속성 1개 일치) 대리점의 건마다 영업지원팀 소명 요청을 연다(R3)."""
    edges = session.scalars(
        select(RelationEdge)
        .join(
            GroupVersion,
            GroupVersion.group_version_id == RelationEdge.group_version_id,
        )
        .where(
            GroupVersion.is_current,
            RelationEdge.judgement == RelationJudgement.CIRCUMSTANTIAL,
        )
    )
    reason_of: dict[str, str] = {}
    for edge in edges:
        # 같은 속성에 값이 둘이어도(05) 속성 이름은 한 번만, 순서는 지킨다.
        attrs = " · ".join(dict.fromkeys(m["attr"] for m in edge.matched_attrs))
        reason = f"{edge.agency_a}–{edge.agency_b} {attrs} 일치(정황)"
        reason_of.setdefault(edge.agency_a, reason)
        reason_of.setdefault(edge.agency_b, reason)

    return [
        create_task(
            session,
            dept=Department.SALES_SUPPORT,
            task_type="소명 요청",
            ref_id=claim.rebate_id,
            detail=reason_of[claim.agency_id],
        )
        for claim in claims
        if claim.agency_id in reason_of
    ]


def change_task_status(session: Session, task_id: int, to_status: TaskStatus) -> Task:
    """사람이 작업을 진행 · 완료로 표시한다.

    완료는 다시 열 수 없고, 상태 전이가 만든 작업은 손으로 닫을 수 없다.
    """
    task = session.get(Task, task_id)
    if task is None:
        raise LookupError(f"작업 {task_id} 이(가) 없습니다")
    if to_status not in TASK_TRANSITIONS.get(task.status, frozenset()):
        raise InvalidTaskTransitionError(
            f"작업 상태를 바꿀 수 없습니다: {task.status} → {to_status} (작업 {task_id})"
        )
    # 전이 작업은 건이 그 상태를 떠날 때 자동으로 닫힌다(on_claim_transition).
    # 그래서 열려 있다면 건은 아직 그 상태다. 손으로 닫으면 처리 안 된 건이 목록에서 사라진다.
    if to_status == TaskStatus.DONE and task.trigger_status is not None:
        raise InvalidTaskTransitionError(
            f"건 {task.ref_id} 이(가) 아직 {task.trigger_status} 상태라 "
            f"'{task.task_type}' 작업을 닫을 수 없습니다. "
            f"건을 처리하면 자동으로 닫힙니다 (작업 {task_id})"
        )
    task.status = to_status
    if to_status == TaskStatus.DONE:
        task.closed_at = func.now()
    session.flush()
    return task
