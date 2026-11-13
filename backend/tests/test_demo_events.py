"""시연 이벤트(26) 테스트.

6월분 접수 뒤 단독 37건(그룹 없는 전결대기)을 한 번에 전결 승인 · 지급 지시하고, 은행 회신 [모의] 을 일괄로 넣는다.
G1 3건(상신대기)과 그룹 G1 은 건드리지 않는다. 숫자: 6월 40건 = 단독 37 + G1 3(3,888,097원).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_review_model
from app.core.database import make_engine
from app.main import create_app
from app.models import EventLog, RebateClaim

G1_CLAIMS = ["RB-00054", "RB-00120", "RB-00180"]


@pytest.fixture
def engine(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    yield eng
    eng.dispose()


@pytest.fixture
def app(tmp_path, engine):
    app = create_app(tmp_path / "missing", engine=engine)
    app.dependency_overrides[get_review_model] = lambda: None
    return app


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        assert c.post("/api/claims/intake", params={"period": "2026-06"}).is_success
        yield c


def june_total(engine) -> int:
    with Session(engine) as session:
        return session.scalar(
            select(func.sum(RebateClaim.rebate_amount_krw)).where(
                RebateClaim.period_ym == "2026-06"
            )
        )


def statuses(engine, rebate_ids) -> list[str]:
    with Session(engine) as session:
        return [session.get(RebateClaim, r).status for r in rebate_ids]


def test_standalone_batch_then_bank_success_pays_37(client, engine):
    """단독 37건이 전결 승인 → 지급지시 → 은행 회신 성공으로 지급완료가 되고 G1 은 상신대기 그대로다."""
    res = client.post(
        "/api/demo/events/standalone-approve", json={"period_ym": "2026-06"}
    )
    assert res.status_code == 200
    batch = res.json()
    assert (batch["approved"], len(batch["payment_ids"])) == (37, 37)
    assert batch["total_krw"] == june_total(engine) - 3_888_097
    assert statuses(engine, G1_CLAIMS) == ["상신대기"] * 3

    res = client.post("/api/demo/events/bank-replies", json={"result": "성공"})
    replies = res.json()
    assert (replies["replied"], replies["total_krw"]) == (37, batch["total_krw"])
    assert replies["by_claim_status"] == {"지급완료": 37}
    with Session(engine) as session:
        # 결정 이력에 시연 사유가 그대로 남아 사람이 한 건씩 누른 것과 구별된다.
        reasons = set(
            session.scalars(select(EventLog.reason).where(EventLog.to_status == "승인"))
        )
    assert reasons == {"시연 일괄 처리(시나리오 1)"}


def test_bank_account_error_puts_claims_on_hold_and_second_run_is_empty(client):
    client.post("/api/demo/events/standalone-approve", json={"period_ym": "2026-06"})
    replies = client.post(
        "/api/demo/events/bank-replies", json={"result": "계좌오류"}
    ).json()
    assert replies["by_claim_status"] == {"지급보류": 37}
    # 기다리는 지시가 없으면 아무것도 하지 않는다(오류 아님).
    again = client.post("/api/demo/events/bank-replies", json={"result": "성공"}).json()
    assert (again["replied"], again["by_claim_status"]) == (0, {})


def test_batch_resumes_pending_ai_review_with_reason(app, client, fake_model):
    """AI 가 반려를 권하며 기다리던 건도 시연 사유가 있어 일괄 승인되고, 추천 행에 불일치로 남는다."""
    answer = {
        "recommendation": "반려",
        "ai_authority": "영업지원팀",
        "group_sum_krw": 988_932,
        "rationale": ["시연용"],
        "counter_evidence": [],
        "confidence": 0.5,
    }
    app.dependency_overrides[get_review_model] = lambda: fake_model(answer)
    assert client.post("/api/claims/RB-00006/review").is_success
    client.post("/api/demo/events/standalone-approve", json={"period_ym": "2026-06"})
    review = client.get("/api/claims/RB-00006").json()["ai_review"]
    assert (review["human_decision"], review["agreed"], review["human_reason"]) == (
        "승인",
        False,
        "시연 일괄 처리(시나리오 1)",
    )


def test_second_batch_and_bad_input(client):
    """두 번째 일괄은 대상이 없어 0건, 대상월 형식 · 회신 값이 틀리면 422."""
    client.post("/api/demo/events/standalone-approve", json={"period_ym": "2026-06"})
    again = client.post(
        "/api/demo/events/standalone-approve", json={"period_ym": "2026-06"}
    ).json()
    assert (again["approved"], again["total_krw"]) == (0, 0)
    assert (
        client.post(
            "/api/demo/events/standalone-approve", json={"period_ym": "2026-6"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/demo/events/bank-replies", json={"result": "보류"}
        ).status_code
        == 422
    )
