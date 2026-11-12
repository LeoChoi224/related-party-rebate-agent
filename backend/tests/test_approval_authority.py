"""결재 권한 테스트.

앞부분은 가짜 장려금 건으로 규칙의 경계(200만원 이하 · 초과, 반려 제외, 그룹 · 달별 합산)를 보고,
뒷부분은 원본 데이터로 완료 기준(G1 6월 3,888,097원 → 영업임원, 단독 D-001 → 영업지원팀)을 본다.
"""

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import RebateClaim
from app.models.enums import ApproverRole, ClaimStatus
from app.services.approval_authority import (
    assess_period,
    current_group_of,
    decide_authority,
    required_authority,
)
from app.services.related_party import find_related_parties, save_group_version

SUPPORT = ApproverRole.SALES_SUPPORT
EXECUTIVE = ApproverRole.SALES_EXECUTIVE
G1 = {"D-011", "D-024", "D-037"}


def claim(
    rebate_id, agency_id, amount, period="2026-06", status=ClaimStatus.NOT_RECEIVED
):
    """DB 에 넣지 않은 장려금 건 한 줄. 계산 함수는 DB 를 몰라도 된다."""
    return RebateClaim(
        rebate_id=rebate_id,
        agency_id=agency_id,
        period_ym=period,
        sales_performance_krw=0,
        rebate_amount_krw=amount,
        status=status,
        original_status="미지급",
        source_file="test.csv",
        source_row=1,
    )


def summary(decisions):
    return [
        (d.rebate_id, d.group_id, d.group_sum_krw, d.min_authority) for d in decisions
    ]


@pytest.mark.parametrize(
    ("group_sum_krw", "expected"),
    [(1_999_999, SUPPORT), (2_000_000, SUPPORT), (2_000_001, EXECUTIVE)],
)
def test_limit_is_two_million_inclusive(group_sum_krw, expected):
    """200만원 '이하'는 전결이다. 정각은 전결, 1원이라도 넘으면 영업임원."""
    assert required_authority(group_sum_krw) == expected


def test_group_claims_are_summed_together():
    """그룹 구성원 건은 합산하고, 그룹이 없는 대리점은 자기 금액만 본다."""
    decisions = decide_authority(
        [
            claim("RB-1", "D-011", 1_500_000),
            claim("RB-2", "D-024", 1_000_000),
            claim("RB-3", "D-001", 1_500_000),
        ],
        {"D-011": 7, "D-024": 7},
    )
    assert summary(decisions) == [
        ("RB-1", 7, 2_500_000, EXECUTIVE),
        ("RB-2", 7, 2_500_000, EXECUTIVE),
        ("RB-3", None, 1_500_000, SUPPORT),
    ]


def test_rejected_claim_is_left_out_of_sum_and_result():
    """반려 건은 지급되지 않으므로 합산에도 결과에도 없다."""
    decisions = decide_authority(
        [
            claim("RB-1", "D-011", 1_500_000),
            claim("RB-2", "D-024", 1_000_000, status=ClaimStatus.REJECTED),
        ],
        {"D-011": 7, "D-024": 7},
    )
    assert summary(decisions) == [("RB-1", 7, 1_500_000, SUPPORT)]


def test_each_month_is_summed_separately():
    """여러 달을 함께 넘겨도 달마다 따로 합산한다."""
    decisions = decide_authority(
        [
            claim("RB-1", "D-011", 1_500_000, period="2026-05"),
            claim("RB-2", "D-024", 1_000_000, period="2026-06"),
        ],
        {"D-011": 7, "D-024": 7},
    )
    assert [d.group_sum_krw for d in decisions] == [1_500_000, 1_000_000]
    assert {d.min_authority for d in decisions} == {SUPPORT}


def test_result_is_sorted_by_rebate_id():
    """입력 순서와 상관없이 rebate_id 순으로 돌려준다."""
    decisions = decide_authority(
        [
            claim("RB-3", "D-003", 1),
            claim("RB-1", "D-001", 1),
            claim("RB-2", "D-002", 1),
        ],
        {},
    )
    assert [d.rebate_id for d in decisions] == ["RB-1", "RB-2", "RB-3"]


def test_one_pass_iterator_is_enough():
    """한 번만 돌 수 있는 반복자를 넘겨도 합산과 판정이 모두 된다."""
    claims = iter(
        [claim("RB-1", "D-011", 1_500_000), claim("RB-2", "D-024", 1_000_000)]
    )
    decisions = decide_authority(claims, {"D-011": 7, "D-024": 7})
    assert [d.group_sum_krw for d in decisions] == [2_500_000, 2_500_000]


def test_empty_or_all_rejected_gives_empty_result():
    """입력이 없거나 모두 반려면 예외 없이 빈 결과다."""
    assert decide_authority([], {}) == []
    rejected = claim("RB-1", "D-001", 1, status=ClaimStatus.REJECTED)
    assert decide_authority([rejected], {}) == []


def test_seeded_claims_are_not_assessed_yet(seeded_engine):
    """앱을 켠 직후 240건은 판정 전이라 세 컬럼이 모두 비어 있다."""
    with Session(seeded_engine) as session:
        assessed = session.scalar(
            select(func.count())
            .select_from(RebateClaim)
            .where(
                RebateClaim.min_authority.is_not(None)
                | RebateClaim.group_id.is_not(None)
                | RebateClaim.group_sum_krw.is_not(None)
            )
        )
        assert assessed == 0


def test_current_group_of_maps_g1_members(seeded_engine):
    """지금 버전 그룹은 G1 하나라 세 대리점만 같은 그룹 ID 를 가리킨다."""
    with Session(seeded_engine) as session:
        group_of = current_group_of(session)
    assert set(group_of) == G1
    assert len(set(group_of.values())) == 1


def test_current_group_of_ignores_old_versions(seeded_engine):
    """다시 계산해 새 버전에 그룹이 없으면, 옛 버전의 G1 은 판정 단위가 아니다."""
    with Session(seeded_engine) as session, session.begin():
        save_group_version(session, find_related_parties([]))
        assert current_group_of(session) == {}


def test_june_g1_goes_to_executive_and_others_to_support(seeded_engine):
    """6월: G1 3건은 3,888,097원으로 영업임원, 나머지 37건은 영업지원팀."""
    with Session(seeded_engine) as session, session.begin():
        decisions = assess_period(session, "2026-06")

    assert len(decisions) == 40
    g1 = [d for d in decisions if d.group_id is not None]
    assert {d.group_sum_krw for d in g1} == {3_888_097}
    assert {d.min_authority for d in g1} == {EXECUTIVE}
    assert len(g1) == 3
    assert sum(d.min_authority == SUPPORT for d in decisions) == 37

    with Session(seeded_engine) as session:
        d001 = session.get(RebateClaim, "RB-00006")
        assert (d001.agency_id, d001.period_ym) == ("D-001", "2026-06")
        assert (d001.group_id, d001.group_sum_krw, d001.min_authority) == (
            None,
            988_932,
            "영업지원팀",
        )
        g1_claims = session.scalars(
            select(RebateClaim)
            .where(RebateClaim.agency_id.in_(G1))
            .where(RebateClaim.period_ym == "2026-06")
        ).all()
        assert {c.min_authority for c in g1_claims} == {"영업임원"}
        # 업무 상태는 그대로다. 전결대기 · 상신대기로 바꾸는 일은 07 · 08 이 한다.
        assert {c.status for c in g1_claims} == {"미접수"}


def test_january_to_may_reveals_15_bypassed_claims(seeded_engine):
    """1~5월: 영업임원 대상인데 원본 결재자가 영업지원팀인 건이 15건, 22,238,349원."""
    with Session(seeded_engine) as session, session.begin():
        for month in range(1, 6):
            assess_period(session, f"2026-{month:02d}")
        bypassed = session.scalars(
            select(RebateClaim).where(
                RebateClaim.min_authority == EXECUTIVE,
                RebateClaim.original_approver == "영업지원팀",
            )
        ).all()
        assert len(bypassed) == 15
        assert {c.agency_id for c in bypassed} == G1
        assert sum(c.rebate_amount_krw for c in bypassed) == 22_238_349


def test_rejected_claims_are_cleared_on_reassessment(seeded_engine):
    """판정 뒤 반려된 건을 다시 판정하면 세 컬럼이 비고, 남은 건의 합만 남는다."""
    with Session(seeded_engine) as session, session.begin():
        assess_period(session, "2026-06")
        session.execute(
            update(RebateClaim)
            .where(RebateClaim.agency_id == "D-024", RebateClaim.period_ym == "2026-06")
            .values(status=ClaimStatus.REJECTED)
        )
        assess_period(session, "2026-06")
        rejected = session.scalars(
            select(RebateClaim).where(
                RebateClaim.agency_id == "D-024", RebateClaim.period_ym == "2026-06"
            )
        ).one()
        assert (rejected.min_authority, rejected.group_id, rejected.group_sum_krw) == (
            None,
            None,
            None,
        )
        d011 = session.scalars(
            select(RebateClaim).where(
                RebateClaim.agency_id == "D-011", RebateClaim.period_ym == "2026-06"
            )
        ).one()
        # 3,888,097 - 1,189,046(D-024) = 2,699,051 이라 여전히 영업임원이다.
        assert (d011.group_sum_krw, d011.min_authority) == (2_699_051, "영업임원")


def test_assess_does_not_commit_by_itself(seeded_engine):
    """판정 함수는 commit 하지 않는다. 트랜잭션 없이 부르고 닫으면 남지 않는다."""
    with Session(seeded_engine) as session:
        assess_period(session, "2026-06")

    with Session(seeded_engine) as session:
        assert session.get(RebateClaim, "RB-00006").min_authority is None


def test_unknown_period_gives_empty_result(seeded_engine):
    """장려금 건이 없는 달은 예외 없이 빈 결과다."""
    with Session(seeded_engine) as session:
        assert assess_period(session, "2026-07") == []
