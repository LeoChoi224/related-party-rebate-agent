"""상신 결재 테스트.

앞부분은 서비스(승인 요청 만들기 · 상신 결정 · 전결 결정)를 원본 6월분 접수 뒤에 부르고,
뒷부분은 API 가 403 · 404 · 409 · 422 를 내는지 본다.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import make_engine
from app.main import create_app
from app.models import ApprovalItem, ApprovalRequest, EventLog, RebateClaim
from app.models.enums import Decision
from app.services.approval import (
    InsufficientAuthorityError,
    decide_approval,
    decide_claim,
)
from app.services.claim_state import InvalidTransitionError
from app.services.intake import intake_period

G1_CLAIMS = ["RB-00054", "RB-00120", "RB-00180"]
# 원본 6월분 D-001 건. 988,932원이라 전결대기로 간다.
D001_JUNE = "RB-00006"
EXECUTIVE = {"actor": "박임원", "role": "영업임원"}
SUPPORT = {"actor": "김지원", "role": "영업지원팀"}


@pytest.fixture
def june_engine(seeded_engine):
    """원본으로 채우고 6월분을 접수까지 마친 임시 DB."""
    with Session(seeded_engine) as session, session.begin():
        intake_period(session, "2026-06")
    return seeded_engine


def statuses(session: Session, rebate_ids: list[str]) -> list[str]:
    return [session.get(RebateClaim, r).status for r in rebate_ids]


def count_events(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(EventLog))


def test_intake_opens_one_request_for_g1(june_engine):
    """6월 접수 직후 승인 요청은 G1 1건(3,888,097원, 영업임원)이고 포함 건은 3건이다."""
    with Session(june_engine) as session:
        request = session.scalars(select(ApprovalRequest)).one()
        assert (request.group_id, request.period_ym) == (1, "2026-06")
        assert (request.group_sum_krw, request.approver_role) == (3_888_097, "영업임원")
        assert request.decision is None
        assert request.decided_at is None
        items = session.scalars(
            select(ApprovalItem.rebate_id).order_by(ApprovalItem.rebate_id)
        ).all()
        assert items == G1_CLAIMS


def test_support_cannot_decide_executive_request(june_engine):
    """로드맵 09 완료 기준: 영업지원팀이 상신 건을 승인하면 거부되고 아무것도 바뀌지 않는다."""
    with Session(june_engine) as session, session.begin():
        with pytest.raises(
            InsufficientAuthorityError, match=r"영업지원팀 은\(는\) 영업임원"
        ):
            decide_approval(session, 1, decision=Decision.APPROVE, reason="", **SUPPORT)
        # 같은 세션 안에서도 그대로다. 권한 검사가 상태 전이보다 앞에 있다는 뜻이다.
        assert statuses(session, G1_CLAIMS) == ["상신대기"] * 3
        assert session.get(ApprovalRequest, 1).decision is None
        assert count_events(session) == 120


def test_executive_approves_request(june_engine):
    """영업임원이 승인하면 3건이 승인되고, 이력에 요청 ID, 요청에 결정자 · 시각이 남는다."""
    with Session(june_engine) as session, session.begin():
        request, claims = decide_approval(
            session, 1, decision=Decision.APPROVE, reason="", **EXECUTIVE
        )
        assert [c.rebate_id for c in claims] == G1_CLAIMS

    with Session(june_engine) as session:
        assert statuses(session, G1_CLAIMS) == ["승인"] * 3
        request = session.get(ApprovalRequest, 1)
        assert (request.decision, request.decided_by) == ("승인", "박임원")
        assert request.reason is None
        assert request.decided_at is not None
        events = session.scalars(
            select(EventLog).where(EventLog.to_status == "승인")
        ).all()
        assert len(events) == 3
        assert {e.reason for e in events} == {"영업임원 승인"}
        assert {e.actor_role for e in events} == {"영업임원"}
        assert {e.payload["request_id"] for e in events} == {1}


def test_executive_rejects_request_with_reason(june_engine):
    """반려하면 3건이 반려되고 사유가 이력과 요청에 함께 남는다."""
    with Session(june_engine) as session, session.begin():
        decide_approval(
            session,
            1,
            decision=Decision.REJECT,
            reason="관련자 관계 소명 먼저",
            **EXECUTIVE,
        )
    with Session(june_engine) as session:
        assert statuses(session, G1_CLAIMS) == ["반려"] * 3
        assert session.get(ApprovalRequest, 1).reason == "관련자 관계 소명 먼저"


def test_decided_request_cannot_be_decided_again(june_engine):
    """이미 결정된 요청은 상태 머신이 막고, 요청의 첫 결정도 그대로다."""
    with Session(june_engine) as session, session.begin():
        decide_approval(session, 1, decision=Decision.APPROVE, reason="", **EXECUTIVE)
    with (
        pytest.raises(InvalidTransitionError, match="승인 → 반려"),
        Session(june_engine) as session,
        session.begin(),
    ):
        decide_approval(
            session, 1, decision=Decision.REJECT, reason="번복", **EXECUTIVE
        )
    with Session(june_engine) as session:
        assert session.get(ApprovalRequest, 1).decision == "승인"


def test_unknown_request_is_lookup_error(june_engine):
    with pytest.raises(LookupError), Session(june_engine) as session:
        decide_approval(session, 9, decision=Decision.APPROVE, reason="", **EXECUTIVE)


@pytest.mark.parametrize("who", [SUPPORT, EXECUTIVE])
def test_support_level_claim_can_be_decided_by_support_or_above(june_engine, who):
    """전결대기 건은 영업지원팀도, 그보다 높은 영업임원도 결정할 수 있다."""
    with Session(june_engine) as session, session.begin():
        claim = decide_claim(
            session, D001_JUNE, decision=Decision.APPROVE, reason="", **who
        )
        assert claim.status == "승인"


def test_finance_role_cannot_decide_claim(june_engine):
    """결재권자가 아닌 역할(재무)은 전결 건도 결정할 수 없다."""
    with pytest.raises(InsufficientAuthorityError), Session(june_engine) as session:
        decide_claim(
            session,
            D001_JUNE,
            decision=Decision.APPROVE,
            reason="",
            actor="이재무",
            role="재무",
        )


def test_executive_claim_cannot_bypass_request(june_engine):
    """상신대기 건은 전결 길로 결정할 수 없다. 영업임원이어도 승인 요청을 거쳐야 한다."""
    with (
        pytest.raises(InvalidTransitionError, match="전결대기 건만"),
        Session(june_engine) as session,
    ):
        decide_claim(
            session, G1_CLAIMS[0], decision=Decision.APPROVE, reason="", **EXECUTIVE
        )


@pytest.fixture
def api_engine(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    yield eng
    eng.dispose()


@pytest.fixture
def client(tmp_path, api_engine):
    """앱이 켜지며 원본으로 채운 뒤 6월분 접수까지 마친 클라이언트."""
    with TestClient(create_app(tmp_path / "missing", engine=api_engine)) as c:
        assert c.post("/api/claims/intake", params={"period": "2026-06"}).is_success
        yield c


def decide_request(client, request_id=1, **body):
    return client.post(f"/api/approvals/{request_id}/decision", json=body)


def test_api_support_approval_is_403(client):
    """영업지원팀이 상신 건을 승인하면 403 과 이유가 온다."""
    res = decide_request(client, decision="승인", **SUPPORT)
    assert res.status_code == 403
    assert res.json() == {
        "detail": "영업지원팀 은(는) 영업임원 결재 건을 결정할 수 없습니다 (요청 1)"
    }


def test_api_reject_without_reason_is_422(client):
    """반려인데 사유가 비어 있으면 스키마 검사에서 422 다."""
    res = decide_request(client, decision="반려", reason="  ", **EXECUTIVE)
    assert res.status_code == 422
    assert "반려 사유를 입력해야 합니다" in res.json()["detail"][0]["msg"]


def test_api_executive_approves_then_second_try_is_409(client, api_engine):
    """영업임원 승인은 200, 같은 요청을 다시 결정하면 409 이고 첫 결정이 남는다."""
    res = decide_request(client, decision="승인", **EXECUTIVE)
    assert res.status_code == 200
    assert res.json() == {
        "request_id": 1,
        "decision": "승인",
        "decided_by": "박임원",
        "rebate_ids": G1_CLAIMS,
        "explanation_ids": [],
    }
    assert decide_request(client, decision="승인", **EXECUTIVE).status_code == 409
    with Session(api_engine) as session:
        assert statuses(session, G1_CLAIMS) == ["승인"] * 3


@pytest.mark.parametrize(
    ("body", "status_code"),
    [
        ({"decision": "보류", **EXECUTIVE}, 422),
        ({"decision": "승인", "actor": "", "role": "영업임원"}, 422),
        ({"decision": "승인", "actor": "박임원"}, 422),
    ],
)
def test_api_malformed_decision_is_422(client, body, status_code):
    """없는 결정 값, 빈 결정자, 빠진 역할은 422 다."""
    assert decide_request(client, **body).status_code == status_code


def test_api_unknown_request_is_404(client):
    assert decide_request(client, 9, decision="승인", **EXECUTIVE).status_code == 404


def test_api_support_decides_claim(client):
    """전결대기 건은 영업지원팀이 결정한다."""
    res = client.post(
        f"/api/claims/{D001_JUNE}/decision", json={"decision": "승인", **SUPPORT}
    )
    assert res.status_code == 200
    assert res.json() == {
        "rebate_id": D001_JUNE,
        "status": "승인",
        "explanation_ids": [],
    }


@pytest.mark.parametrize(
    ("rebate_id", "body", "status_code"),
    [
        (D001_JUNE, {"actor": "이재무", "role": "재무"}, 403),
        (G1_CLAIMS[0], EXECUTIVE, 409),
        ("RB-99999", SUPPORT, 404),
    ],
)
def test_api_claim_decision_errors(client, rebate_id, body, status_code):
    """재무 역할은 403, 상신 건을 전결 길로 보내면 409, 없는 건은 404."""
    res = client.post(
        f"/api/claims/{rebate_id}/decision", json={"decision": "승인", **body}
    )
    assert res.status_code == status_code
