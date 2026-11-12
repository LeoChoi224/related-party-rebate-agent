"""장려금 건 상태 머신.

전이표(ALLOWED_TRANSITIONS)는 데이터이고, docs/architecture.md 5장 그림과 같다.
허용 여부 확인 → 상태 변경 → EventLog 한 줄 → 부서별 작업(task_dispatcher)이
transition 한 함수에서 함께 일어난다.
그래프의 apply 노드와 API 는 상태를 바꿀 때 반드시 여기를 거친다.
누가 어떤 전이를 할 수 있는지(역할 권한)는 09 에서 이 함수를 부르기 전에 검사한다.
"""

from sqlalchemy.orm import Session

from app.models import EventLog, RebateClaim
from app.models.enums import ClaimStatus as S
from app.services.task_dispatcher import on_claim_transition

# 재검토필요(마스터 정정 · 그룹 버전 변경)로 갈 수 있는 상태: 아직 돈이 나가지 않은 것.
# 지급지시는 은행에 보낸 지시를 되돌릴 수 없고, 지급완료 · 상계완료는 끝난 건이라 뺀다.
REVIEW_FROM = frozenset(
    {
        S.RECEIVED,
        S.RELATION_CHECKED,
        S.AWAITING_SUPPORT,
        S.AWAITING_EXECUTIVE,
        S.AWAITING_EXPLANATION,
        S.ON_HOLD,
        S.APPROVED,
        S.REJECTED,
        S.OFFSET_REVIEW,
    }
)

_BASE_TRANSITIONS: dict[S, frozenset[S]] = {
    S.NOT_RECEIVED: frozenset({S.RECEIVED}),
    S.RECEIVED: frozenset({S.RELATION_CHECKED}),
    S.RELATION_CHECKED: frozenset(
        {S.AWAITING_SUPPORT, S.AWAITING_EXECUTIVE, S.AWAITING_EXPLANATION}
    ),
    S.AWAITING_SUPPORT: frozenset(
        {S.APPROVED, S.REJECTED, S.AWAITING_EXECUTIVE, S.AWAITING_EXPLANATION}
    ),
    S.AWAITING_EXECUTIVE: frozenset({S.APPROVED, S.REJECTED, S.AWAITING_EXPLANATION}),
    S.AWAITING_EXPLANATION: frozenset({S.RELATION_CHECKED, S.ON_HOLD}),
    # 증빙 부족이면 추가 소명, 은행 계좌 오류면 확인 뒤 재지시.
    S.ON_HOLD: frozenset({S.AWAITING_EXPLANATION, S.PAYMENT_ORDERED}),
    S.APPROVED: frozenset({S.OFFSET_REVIEW, S.PAYMENT_ORDERED}),
    S.REJECTED: frozenset({S.AWAITING_EXPLANATION}),
    S.OFFSET_REVIEW: frozenset({S.PAYMENT_ORDERED, S.OFFSET_DONE}),
    S.PAYMENT_ORDERED: frozenset({S.PAID, S.ON_HOLD}),
    S.PAID: frozenset(),
    S.OFFSET_DONE: frozenset(),
    S.NEEDS_REVIEW: frozenset({S.RELATION_CHECKED}),
}

# 그림의 화살표에, 9개 상태 → 재검토필요 화살표를 한 번에 더한다.
ALLOWED_TRANSITIONS: dict[S, frozenset[S]] = {
    status: targets
    | (frozenset({S.NEEDS_REVIEW}) if status in REVIEW_FROM else frozenset())
    for status, targets in _BASE_TRANSITIONS.items()
}


class InvalidTransitionError(ValueError):
    """전이표에 없는 상태 전이."""


def can_transition(from_status: str, to_status: str) -> bool:
    """전이표만 보고 허용 여부를 답한다. 상태는 바꾸지 않는다.

    DB 에서 읽은 status 는 문자열이지만 StrEnum 키와 같은 값으로 찾아진다.
    """
    return to_status in ALLOWED_TRANSITIONS.get(from_status, frozenset())


def transition(
    session: Session,
    claim: RebateClaim,
    to_status: S,
    *,
    actor: str,
    actor_role: str,
    reason: str,
    payload: dict | None = None,
) -> EventLog:
    """허용된 전이만 통과시키고, 상태를 바꾸고, 이력 한 줄을 남긴다. commit 하지 않는다.

    역할 권한은 검사하지 않는다(09 가 이 함수를 부르기 전에 한다).
    이력을 남긴 뒤 부서별 작업을 배정한다(10).
    """
    # 입력이 빠진 것은 상태 규칙 위반이 아니라 입력 오류라 예외 종류를 나눈다(API 422).
    if not actor.strip() or not reason.strip():
        raise ValueError(
            f"{claim.rebate_id}: 상태를 바꾼 사람과 이유는 비울 수 없습니다"
        )
    # 확인을 맨 앞에 둔다. 예외가 나면 상태도 이력도 아직 아무것도 바뀌지 않았다.
    if not can_transition(claim.status, to_status):
        raise InvalidTransitionError(
            f"허용되지 않은 상태 전이입니다: {claim.status} → {to_status} "
            f"({claim.rebate_id})"
        )

    # from_status 는 상태를 바꾸기 전에 읽어야 한다.
    event = EventLog(
        actor=actor,
        actor_role=actor_role,
        entity_type="rebate_claim",
        entity_id=claim.rebate_id,
        from_status=claim.status,
        to_status=to_status,
        reason=reason,
        payload=payload,
    )
    claim.status = to_status
    session.add(event)
    # 작업이 이 이력 번호를 가리키므로 flush 로 event_id 를 먼저 받는다.
    session.flush()
    on_claim_transition(session, claim, event)
    return event
