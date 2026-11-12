"""6월분 접수 테스트.

앞부분은 서비스(intake_period)를 원본 데이터로 직접 부르고,
뒷부분은 API(POST /api/claims/intake)가 같은 결과와 409 · 404 · 422 를 내는지 본다.
"""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.database import make_engine
from app.main import create_app
from app.models import EventLog, RebateClaim
from app.models.enums import ClaimStatus
from app.services.claim_state import InvalidTransitionError
from app.services.intake import intake_period

G1 = {"D-011", "D-024", "D-037"}
# 원본 6월분 마지막 건(D-049). rebate_id 순으로 처리하므로 가장 늦게 막힌다.
LAST_JUNE = "RB-00240"


def june_claims(session: Session) -> list[RebateClaim]:
    return session.scalars(
        select(RebateClaim).where(RebateClaim.period_ym == "2026-06")
    ).all()


def count_events(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(EventLog))


def test_june_intake_routes_37_to_support_and_g1_to_executive(seeded_engine):
    """로드맵 08 완료 기준: 6월 40건 → 전결대기 37 + 상신대기 3(G1)."""
    with Session(seeded_engine) as session, session.begin():
        by_status = intake_period(session, "2026-06")
    assert by_status == {"전결대기": 37, "상신대기": 3}
    # StrEnum 은 str 과 == 로 같아 위 비교로는 못 잡는다. 키가 순수 str 인지 따로 본다.
    assert {type(key) for key in by_status} == {str}

    with Session(seeded_engine) as session:
        executive = {
            c.agency_id for c in june_claims(session) if c.status == "상신대기"
        }
        assert executive == G1
        assert {c.min_authority for c in june_claims(session)} == {
            "영업지원팀",
            "영업임원",
        }
        assert count_events(session) == 120


def test_g1_history_explains_why_it_went_to_executive(seeded_engine):
    """G1 건의 이력 3줄에 판정 근거(그룹 · 3,888,097원 · 영업임원)가 남는다."""
    with Session(seeded_engine) as session, session.begin():
        intake_period(session, "2026-06")

    with Session(seeded_engine) as session:
        events = session.scalars(
            select(EventLog)
            .where(EventLog.entity_id == "RB-00054")
            .order_by(EventLog.event_id)
        ).all()
        assert [e.to_status for e in events] == ["접수", "관계확인", "상신대기"]
        assert events[0].reason == "2026-06분 접수"
        assert events[1].payload == {
            "group_id": 1,
            "group_sum_krw": 3_888_097,
            "min_authority": "영업임원",
        }
        assert events[2].reason == "판정 단위 합산 3,888,097원 → 최소 결재권자 영업임원"
        assert {e.actor for e in events} == {"시스템"}


def test_circumstantial_pair_is_not_held(seeded_engine):
    """정황(D-034 · D-041)은 지급을 막지 않으므로 전결대기로 간다(소명 작업은 10)."""
    with Session(seeded_engine) as session, session.begin():
        intake_period(session, "2026-06")
    with Session(seeded_engine) as session:
        statuses = {
            c.agency_id: c.status
            for c in june_claims(session)
            if c.agency_id in {"D-034", "D-041"}
        }
    assert statuses == {"D-034": "전결대기", "D-041": "전결대기"}


def test_second_intake_is_blocked_by_state_machine(seeded_engine):
    """같은 달을 다시 접수하면 상태 머신이 막는다. 첫 건(RB-00006)에서 멈춘다."""
    with Session(seeded_engine) as session, session.begin():
        intake_period(session, "2026-06")
    with (
        pytest.raises(InvalidTransitionError, match=r"전결대기 → 접수 \(RB-00006\)"),
        Session(seeded_engine) as session,
        session.begin(),
    ):
        intake_period(session, "2026-06")
    with Session(seeded_engine) as session:
        assert count_events(session) == 120


def test_one_blocked_claim_rolls_back_the_whole_month(seeded_engine):
    """마지막 건 하나가 미접수가 아니면, 앞서 접수한 39건까지 모두 되돌아간다."""
    with Session(seeded_engine) as session, session.begin():
        session.execute(
            update(RebateClaim)
            .where(RebateClaim.rebate_id == LAST_JUNE)
            .values(status=ClaimStatus.REJECTED)
        )
    with (
        pytest.raises(InvalidTransitionError, match=LAST_JUNE),
        Session(seeded_engine) as session,
        session.begin(),
    ):
        intake_period(session, "2026-06")
    with Session(seeded_engine) as session:
        statuses = [c.status for c in june_claims(session)]
        assert statuses.count("미접수") == 39
        assert count_events(session) == 0


def test_already_paid_month_is_blocked(seeded_engine):
    """1~5월은 지급완료 · 반려라 접수할 수 없다."""
    with (
        pytest.raises(InvalidTransitionError),
        Session(seeded_engine) as session,
        session.begin(),
    ):
        intake_period(session, "2026-05")


def test_month_without_claims_is_lookup_error(seeded_engine):
    """장려금 건이 없는 달은 LookupError 다(API 는 404)."""
    with (
        pytest.raises(LookupError, match="2026-07 장려금 건이 없습니다"),
        Session(seeded_engine) as session,
    ):
        intake_period(session, "2026-07")


def test_intake_logs_korean_summary(seeded_engine, caplog):
    """접수 결과를 한글 로그로 남긴다."""
    with (
        caplog.at_level(logging.INFO, logger="app.services.intake"),
        Session(seeded_engine) as session,
        session.begin(),
    ):
        intake_period(session, "2026-06")
    assert "2026-06 장려금 40건을 접수했습니다" in caplog.text


@pytest.fixture
def api_engine(tmp_path):
    """API 테스트용 빈 임시 DB. 앱이 켜지며 원본으로 채운다."""
    eng = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    yield eng
    eng.dispose()


@pytest.fixture
def client(tmp_path, api_engine):
    with TestClient(create_app(tmp_path / "missing", engine=api_engine)) as c:
        yield c


def intake(client, period="2026-06"):
    return client.post("/api/claims/intake", params={"period": period})


def test_api_intake_returns_summary(client, api_engine):
    """200 과 요약. DB 에도 commit 돼 있다."""
    res = intake(client)
    assert res.status_code == 200
    assert res.json() == {
        "period_ym": "2026-06",
        "received": 40,
        "by_status": {"전결대기": 37, "상신대기": 3},
    }
    with Session(api_engine) as session:
        assert count_events(session) == 120


def test_api_second_intake_is_409_and_changes_nothing(client, api_engine):
    """다시 누르면 409 와 막힌 건 · 상태가 보이고, 이력은 120줄 그대로다."""
    intake(client)
    res = intake(client)
    assert res.status_code == 409
    assert res.json() == {
        "detail": "허용되지 않은 상태 전이입니다: 전결대기 → 접수 (RB-00006)"
    }
    with Session(api_engine) as session:
        assert count_events(session) == 120


@pytest.mark.parametrize(
    ("period", "status_code"),
    [("2026-05", 409), ("2026-07", 404), ("2026-6", 422), ("2026-13", 422)],
)
def test_api_rejects_processed_missing_and_malformed_months(
    client, period, status_code
):
    """1~5월은 이미 처리돼 409, 건이 없는 달은 404, 형식이 틀리면 422."""
    assert intake(client, period).status_code == status_code


def test_api_period_is_required(client):
    """대상월을 빠뜨리면 422 다."""
    assert client.post("/api/claims/intake").status_code == 422


def test_api_intake_again_after_demo_reset(client):
    """시연 초기화 뒤에는 같은 달을 다시 접수할 수 있다."""
    assert intake(client).status_code == 200
    assert client.post("/api/demo/reset").status_code == 200
    assert intake(client).status_code == 200
