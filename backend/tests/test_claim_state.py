"""상태 머신 테스트.

앞부분은 전이표 자체(빠진 상태, 끝 상태, 도달 가능성, 재검토필요 범위, Step 1 결정)를 보고,
뒷부분은 전이 함수가 허용되지 않은 전이를 막고 모든 전이를 이력에 남기는지 본다.
"""

from collections import deque

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EventLog, RebateClaim
from app.models.enums import ClaimStatus as S
from app.services.claim_state import (
    ALLOWED_TRANSITIONS,
    REVIEW_FROM,
    InvalidTransitionError,
    can_transition,
    transition,
)

# 원본 6월분 G1 의 D-011 건. 시더가 미접수로 넣는다.
G1_JUNE = "RB-00054"
# 원본 1월분 D-001 건. 시더가 지급완료로 넣는다.
PAID_JANUARY = "RB-00001"
WHO = {"actor": "시스템", "actor_role": "시스템"}


def test_every_status_has_a_row():
    """14개 상태가 모두 전이표에 있다. 빠지면 그 상태에서는 어디로도 못 간다."""
    assert set(ALLOWED_TRANSITIONS) == set(S)


def test_terminal_statuses_go_nowhere():
    """끝 상태는 지급완료 · 상계완료 둘뿐이다."""
    terminal = {
        status for status, targets in ALLOWED_TRANSITIONS.items() if not targets
    }
    assert terminal == {S.PAID, S.OFFSET_DONE}


def test_every_status_is_reachable_from_not_received():
    """미접수에서 출발해 화살표를 따라가면 14개 상태 모두에 닿는다(너비 우선 탐색)."""
    seen = {S.NOT_RECEIVED}
    queue = deque([S.NOT_RECEIVED])
    while queue:
        for nxt in ALLOWED_TRANSITIONS[queue.popleft()]:
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    assert seen == set(S)


def test_needs_review_comes_only_from_unpaid_statuses():
    """재검토필요로 들어오는 상태는 돈이 나가지 않은 9개뿐이다."""
    incoming = {
        s for s, targets in ALLOWED_TRANSITIONS.items() if S.NEEDS_REVIEW in targets
    }
    assert incoming == REVIEW_FROM
    assert len(incoming) == 9
    assert incoming.isdisjoint({S.PAYMENT_ORDERED, S.PAID, S.OFFSET_DONE})


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        (S.NOT_RECEIVED, S.RECEIVED),
        (S.RELATION_CHECKED, S.AWAITING_EXECUTIVE),
        (S.AWAITING_EXECUTIVE, S.APPROVED),
        # Step 1 결정 1: 전결권자도 반려할 수 있다.
        (S.AWAITING_SUPPORT, S.REJECTED),
        # Step 1 결정 2: 지급보류의 두 출구.
        (S.ON_HOLD, S.AWAITING_EXPLANATION),
        (S.ON_HOLD, S.PAYMENT_ORDERED),
        (S.PAYMENT_ORDERED, S.ON_HOLD),
        (S.APPROVED, S.NEEDS_REVIEW),
    ],
)
def test_allowed_transitions(from_status, to_status):
    assert can_transition(from_status, to_status)


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        (S.PAID, S.APPROVED),
        (S.NOT_RECEIVED, S.APPROVED),
        (S.AWAITING_EXECUTIVE, S.PAID),
        (S.PAYMENT_ORDERED, S.NEEDS_REVIEW),
        # 같은 상태로 가는 화살표는 없다.
        (S.APPROVED, S.APPROVED),
    ],
)
def test_denied_transitions(from_status, to_status):
    assert not can_transition(from_status, to_status)


def test_plain_strings_from_db_work():
    """DB 에서 읽은 상태는 str 이다. enum 으로 바꾸지 않아도 같은 답이 나온다."""
    assert can_transition("상신대기", "승인")
    assert not can_transition("지급완료", "승인")


def test_unknown_status_is_not_allowed():
    """표에 없는 상태(오타 등)는 예외 없이 거부된다."""
    assert not can_transition("보류중", S.APPROVED)
    assert not can_transition(S.APPROVED, "보류중")


def count_events(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(EventLog))


def test_seeded_db_has_no_events(seeded_engine):
    """원본에서 옮긴 첫 상태는 전이가 아니라 이력이 없다."""
    with Session(seeded_engine) as session:
        assert count_events(session) == 0


def test_allowed_transition_changes_status_and_logs_one_event(seeded_engine):
    """허용된 전이는 상태를 바꾸고 누가 · 역할 · 이전 → 이후 · 이유 · 추가 정보를 남긴다."""
    with Session(seeded_engine) as session, session.begin():
        claim = session.get(RebateClaim, G1_JUNE)
        transition(
            session,
            claim,
            S.RECEIVED,
            actor="홍길동",
            actor_role="영업지원팀",
            reason="6월분 접수",
            payload={"period_ym": "2026-06"},
        )

    with Session(seeded_engine) as session:
        assert session.get(RebateClaim, G1_JUNE).status == "접수"
        event = session.scalars(select(EventLog)).one()
        assert (event.actor, event.actor_role) == ("홍길동", "영업지원팀")
        assert (event.entity_type, event.entity_id) == ("rebate_claim", G1_JUNE)
        assert (event.from_status, event.to_status) == ("미접수", "접수")
        assert event.reason == "6월분 접수"
        assert event.payload == {"period_ym": "2026-06"}
        assert event.ts is not None


def test_denied_transition_changes_nothing(seeded_engine):
    """로드맵 07 완료 기준: 지급완료 → 승인 은 예외가 나고 상태도 이력도 그대로다."""
    with Session(seeded_engine) as session, session.begin():
        claim = session.get(RebateClaim, PAID_JANUARY)
        with pytest.raises(InvalidTransitionError, match="지급완료 → 승인"):
            transition(session, claim, S.APPROVED, reason="다시 승인", **WHO)
        assert claim.status == "지급완료"
        assert count_events(session) == 0


@pytest.mark.parametrize(
    ("actor", "reason"),
    [("시스템", ""), ("시스템", "   "), ("", "6월분 접수")],
)
def test_blank_actor_or_reason_is_rejected(seeded_engine, actor, reason):
    """누가 · 이유가 비어 있으면 입력 오류다. 상태도 이력도 그대로다."""
    with Session(seeded_engine) as session, session.begin():
        claim = session.get(RebateClaim, G1_JUNE)
        with pytest.raises(ValueError, match="비울 수 없습니다") as caught:
            transition(
                session,
                claim,
                S.RECEIVED,
                actor=actor,
                actor_role="시스템",
                reason=reason,
            )
        # 전이 규칙 위반과 섞이지 않게 예외 종류가 다르다.
        assert not isinstance(caught.value, InvalidTransitionError)
        assert claim.status == "미접수"
        assert count_events(session) == 0


def test_intake_flow_leaves_three_events_in_order(seeded_engine):
    """08 의 흐름(미접수 → 접수 → 관계확인 → 상신대기)이 이력 3줄로 순서대로 남는다."""
    steps = [
        (S.RECEIVED, "6월분 접수"),
        (S.RELATION_CHECKED, "관련자 · 한도 판정"),
        (S.AWAITING_EXECUTIVE, "G1 합산 3,888,097원 > 200만원"),
    ]
    with Session(seeded_engine) as session, session.begin():
        claim = session.get(RebateClaim, G1_JUNE)
        for to_status, reason in steps:
            transition(session, claim, to_status, reason=reason, **WHO)

    with Session(seeded_engine) as session:
        events = session.scalars(select(EventLog).order_by(EventLog.event_id)).all()
        assert [(e.from_status, e.to_status) for e in events] == [
            ("미접수", "접수"),
            ("접수", "관계확인"),
            ("관계확인", "상신대기"),
        ]
        assert session.get(RebateClaim, G1_JUNE).status == "상신대기"


def test_role_is_recorded_but_not_checked(seeded_engine):
    """역할 권한은 09 에서 검사한다. 상태 머신은 영업지원팀의 상신 건 승인도 기록만 한다."""
    with Session(seeded_engine) as session, session.begin():
        claim = session.get(RebateClaim, G1_JUNE)
        for to_status in (S.RECEIVED, S.RELATION_CHECKED, S.AWAITING_EXECUTIVE):
            transition(session, claim, to_status, reason="준비", **WHO)
        event = transition(
            session,
            claim,
            S.APPROVED,
            actor="홍길동",
            actor_role="영업지원팀",
            reason="권한 검사 없음을 확인",
        )
        assert (event.from_status, event.actor_role) == ("상신대기", "영업지원팀")


def test_transition_does_not_commit_by_itself(seeded_engine):
    """전이 함수는 commit 하지 않는다. 트랜잭션 없이 부르고 닫으면 남지 않는다."""
    with Session(seeded_engine) as session:
        claim = session.get(RebateClaim, G1_JUNE)
        transition(session, claim, S.RECEIVED, reason="6월분 접수", **WHO)

    with Session(seeded_engine) as session:
        assert session.get(RebateClaim, G1_JUNE).status == "미접수"
        assert count_events(session) == 0
