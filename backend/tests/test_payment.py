"""지급 · 모의 은행 테스트.

앞부분은 서비스(지급 지시 · 은행 회신)를 원본 6월분 접수 · 전결 승인 뒤에 보고,
뒷부분은 API 가 403 · 404 · 409 · 422 를 내는지 본다.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import make_engine
from app.main import create_app
from app.models import EventLog, PaymentOrder, RebateClaim, Task
from app.models.enums import BankResult, ClaimStatus, Decision
from app.services.approval import InsufficientAuthorityError, decide_claim
from app.services.claim_state import InvalidTransitionError, transition
from app.services.intake import intake_period
from app.services.payment import apply_bank_reply, last_payment, order_payment

# 원본 6월분 D-001 건(988,932원, 전결대기 → 테스트에서 승인).
D001_JUNE = "RB-00006"
# 원본 6월분 D-002 건. 승인하지 않고 전결대기로 둔다.
D002_JUNE = "RB-00012"
FINANCE = {"actor": "이재무", "role": "재무"}


@pytest.fixture
def approved_engine(seeded_engine):
    """6월분 접수 뒤 D-001 건을 영업지원팀이 전결 승인한 임시 DB."""
    with Session(seeded_engine) as session, session.begin():
        intake_period(session, "2026-06")
        decide_claim(
            session,
            D001_JUNE,
            decision=Decision.APPROVE,
            reason="",
            actor="김지원",
            role="영업지원팀",
        )
    return seeded_engine


def status_of(session: Session, rebate_id: str) -> str:
    return session.get(RebateClaim, rebate_id).status


def tasks_of(session: Session, rebate_id: str) -> list[tuple[str, str]]:
    tasks = session.scalars(
        select(Task).where(Task.ref_id == rebate_id).order_by(Task.task_id)
    )
    return [(t.task_type, t.status) for t in tasks]


def test_finance_orders_payment_and_closes_payment_task(approved_engine):
    """재무가 지시하면 건이 지급지시가 되고, 지급 실행 작업이 자동으로 닫힌다."""
    with Session(approved_engine) as session, session.begin():
        order = order_payment(session, D001_JUNE, **FINANCE)
        assert (order.payment_id, order.amount_krw, order.status) == (
            1,
            988_932,
            "회신대기",
        )

    with Session(approved_engine) as session:
        assert status_of(session, D001_JUNE) == "지급지시"
        assert tasks_of(session, D001_JUNE) == [("지급 실행", "완료")]


def test_success_reply_marks_claim_paid(approved_engine):
    """로드맵 11 완료 기준: 성공 회신이면 건이 지급완료가 된다. 회신은 출처 '모의'다."""
    with Session(approved_engine) as session, session.begin():
        order = order_payment(session, D001_JUNE, **FINANCE)
        _, reply, claim = apply_bank_reply(
            session, order.payment_id, BankResult.SUCCESS
        )
        assert (reply.result, reply.provenance) == ("성공", "모의")
        assert claim.status == "지급완료"

    with Session(approved_engine) as session:
        assert session.get(PaymentOrder, 1).status == "성공"
        event = session.scalars(
            select(EventLog).where(EventLog.to_status == "지급완료")
        ).one()
        assert (event.actor, event.actor_role) == ("은행", "모의 외부")
        assert event.reason == "은행 회신 성공 [모의]"
        assert event.payload == {"payment_id": 1, "reply_id": 1}


def test_account_error_then_retry_then_success(approved_engine):
    """계좌오류 → 지급보류 · 계좌 확인 작업 → 새 지시 → 확인 작업 닫힘 → 성공 → 지급완료."""
    with Session(approved_engine) as session, session.begin():
        first = order_payment(session, D001_JUNE, **FINANCE)
        apply_bank_reply(session, first.payment_id, BankResult.ACCOUNT_ERROR)
        assert status_of(session, D001_JUNE) == "지급보류"
        assert tasks_of(session, D001_JUNE)[-1] == ("지급 계좌 확인", "열림")

        second = order_payment(session, D001_JUNE, **FINANCE)
        assert second.payment_id == 2
        assert last_payment(session, D001_JUNE) is second
        assert tasks_of(session, D001_JUNE)[-1] == ("지급 계좌 확인", "완료")

        apply_bank_reply(session, second.payment_id, BankResult.SUCCESS)
        assert status_of(session, D001_JUNE) == "지급완료"
        # 앞의 지시는 계좌오류 기록으로 그대로 남는다.
        assert session.get(PaymentOrder, 1).status == "계좌오류"


@pytest.mark.parametrize("role", ["영업임원", "영업지원팀"])
def test_only_finance_can_order(approved_engine, role):
    """재무가 아니면 결재권이 높아도 지급을 지시할 수 없다. 아무것도 바뀌지 않는다."""
    with Session(approved_engine) as session, session.begin():
        with pytest.raises(InsufficientAuthorityError, match="재무만 지시합니다"):
            order_payment(session, D001_JUNE, actor="박임원", role=role)
        assert status_of(session, D001_JUNE) == "승인"
        assert last_payment(session, D001_JUNE) is None


def test_claim_before_approval_cannot_be_paid(approved_engine):
    """승인 전(전결대기) 건은 지급을 지시할 수 없다."""
    with (
        pytest.raises(InvalidTransitionError, match="전결대기"),
        Session(approved_engine) as session,
    ):
        order_payment(session, D002_JUNE, **FINANCE)


def test_on_hold_for_missing_evidence_cannot_be_paid(approved_engine):
    """증빙 부족으로 지급보류된 건은 지급 기록이 없어 다시 지시할 수 없다(소명을 건너뛰지 못함)."""
    with Session(approved_engine) as session, session.begin():
        claim = session.get(RebateClaim, D002_JUNE)
        for to_status in (ClaimStatus.AWAITING_EXPLANATION, ClaimStatus.ON_HOLD):
            transition(
                session,
                claim,
                to_status,
                actor="시스템",
                actor_role="시스템",
                reason="증빙 부족",
            )
        with pytest.raises(InvalidTransitionError, match="지급보류"):
            order_payment(session, D002_JUNE, **FINANCE)


def test_second_reply_is_blocked(approved_engine):
    """같은 지시에 회신을 두 번 넣을 수 없다. 첫 회신이 그대로 남는다."""
    with Session(approved_engine) as session, session.begin():
        order = order_payment(session, D001_JUNE, **FINANCE)
        apply_bank_reply(session, order.payment_id, BankResult.ACCOUNT_ERROR)
        with pytest.raises(InvalidTransitionError, match="이미 회신을 받은"):
            apply_bank_reply(session, order.payment_id, BankResult.SUCCESS)
        assert status_of(session, D001_JUNE) == "지급보류"


def test_unknown_claim_or_payment_is_lookup_error(approved_engine):
    with Session(approved_engine) as session:
        with pytest.raises(LookupError):
            order_payment(session, "RB-99999", **FINANCE)
        with pytest.raises(LookupError):
            apply_bank_reply(session, 99, BankResult.SUCCESS)


@pytest.fixture
def api_engine(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    yield eng
    eng.dispose()


@pytest.fixture
def client(tmp_path, api_engine):
    """앱이 켜지며 원본으로 채운 뒤 6월분 접수와 D-001 전결 승인까지 마친 클라이언트."""
    with TestClient(create_app(tmp_path / "missing", engine=api_engine)) as c:
        assert c.post("/api/claims/intake", params={"period": "2026-06"}).is_success
        approve = {"decision": "승인", "reason": "", "actor": "김지원"}
        res = c.post(
            f"/api/claims/{D001_JUNE}/decision", json={**approve, "role": "영업지원팀"}
        )
        assert res.is_success
        yield c


def order_api(client, rebate_id=D001_JUNE, **body):
    return client.post(f"/api/claims/{rebate_id}/payment-order", json=body or FINANCE)


def reply_api(client, payment_id=1, result="성공"):
    return client.post(
        f"/api/payments/{payment_id}/bank-reply", json={"result": result}
    )


def test_api_order_then_success_reply(client):
    """재무 지시 200(건 지급지시) → 성공 회신 200(건 지급완료, 출처 모의)."""
    res = order_api(client)
    assert res.status_code == 200
    assert res.json() == {
        "payment_id": 1,
        "rebate_id": D001_JUNE,
        "amount_krw": 988_932,
        "status": "회신대기",
        "claim_status": "지급지시",
    }
    res = reply_api(client)
    assert res.status_code == 200
    assert res.json() == {
        "payment_id": 1,
        "result": "성공",
        "provenance": "모의",
        "claim_status": "지급완료",
    }


def test_api_second_reply_is_409(client):
    """같은 지시에 회신을 두 번 넣으면 409 다."""
    order_api(client)
    assert reply_api(client, result="계좌오류").json()["claim_status"] == "지급보류"
    res = reply_api(client)
    assert res.status_code == 409
    assert res.json() == {
        "detail": "이미 회신을 받은 지급 지시입니다: 계좌오류 (지급 1)"
    }


@pytest.mark.parametrize(
    ("rebate_id", "body", "status_code"),
    [
        (D001_JUNE, {"actor": "박임원", "role": "영업임원"}, 403),
        (D002_JUNE, FINANCE, 409),
        ("RB-99999", FINANCE, 404),
        (D001_JUNE, {"actor": "", "role": "재무"}, 422),
    ],
)
def test_api_order_errors(client, rebate_id, body, status_code):
    """영업임원 403, 승인 전 건 409, 없는 건 404, 빈 처리자 422."""
    assert order_api(client, rebate_id, **body).status_code == status_code


@pytest.mark.parametrize(
    ("payment_id", "result", "status_code"),
    [(99, "성공", 404), (1, "보류", 422), (1, "회신대기", 422)],
)
def test_api_reply_errors(client, payment_id, result, status_code):
    """없는 지시 404. 회신 결과에는 성공 · 계좌오류만 된다(회신대기도 422)."""
    order_api(client)
    assert reply_api(client, payment_id, result).status_code == status_code
