"""AI 검토 API 와 결정 API 의 재개 연결 테스트.

모델 의존성을 가짜 모델로 바꿔 진짜 키 · 네트워크 없이 API 끝까지 본다.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_review_model
from app.core.database import make_engine
from app.main import create_app

G1_SUM = 3_888_097
EXECUTIVE = {"actor": "박임원", "role": "영업임원"}
SUPPORT = {"actor": "김지원", "role": "영업지원팀"}


def answer(**overrides) -> dict:
    values = {
        "recommendation": "승인",
        "ai_authority": "영업지원팀",
        "group_sum_krw": G1_SUM,
        "rationale": ["G1 합산이 한도를 넘음"],
        "counter_evidence": ["D-024 실입금계좌가 G1 공유계좌"],
        "confidence": 0.7,
    }
    return values | overrides


@pytest.fixture
def api_engine(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    yield eng
    eng.dispose()


@pytest.fixture
def app(tmp_path, api_engine):
    return create_app(tmp_path / "missing", engine=api_engine)


@pytest.fixture
def client(app):
    """6월분 접수까지 마친 클라이언트."""
    with TestClient(app) as c:
        assert c.post("/api/claims/intake", params={"period": "2026-06"}).is_success
        yield c


def use_model(app, model):
    app.dependency_overrides[get_review_model] = lambda: model


def detail(client, rebate_id):
    return client.get(f"/api/claims/{rebate_id}").json()


def test_review_g1_raises_authority_and_shows_on_every_member(app, client, fake_model):
    use_model(app, fake_model(answer()))
    res = client.post("/api/claims/RB-00054/review")
    assert res.status_code == 200
    body = res.json()
    assert body["target_type"] == "approval_request"
    assert (body["ai_authority"], body["min_authority"]) == ("영업지원팀", "영업임원")
    assert body["authority_raised"] is True
    assert body["created_at"].endswith("Z")
    # 같은 승인 요청의 다른 건 상세에도 같은 추천이 보인다.
    assert detail(client, "RB-00180")["ai_review"]["rec_id"] == body["rec_id"]


def test_forbidden_decision_does_not_reach_graph(app, client, fake_model):
    """영업지원팀 승인이 403 으로 막힌 뒤 영업임원이 반려하면 반려로 기록된다."""
    use_model(app, fake_model(answer()))
    client.post("/api/claims/RB-00054/review")
    request_id = detail(client, "RB-00054")["approval"]["request_id"]
    url = f"/api/approvals/{request_id}/decision"

    denied = client.post(url, json={"decision": "승인", "reason": "", **SUPPORT})
    assert denied.status_code == 403

    reject = {"decision": "반려", "reason": "관련자 그룹 증빙 요청", **EXECUTIVE}
    assert client.post(url, json=reject).status_code == 200

    rec = detail(client, "RB-00054")["ai_review"]
    assert rec["human_decision"] == "반려"
    assert rec["human_reason"] == "관련자 그룹 증빙 요청"
    assert rec["decided_by"] == "박임원"
    assert rec["agreed"] is False
    assert detail(client, "RB-00120")["status"] == "반려"


def test_support_decision_resumes_claim_review(app, client, fake_model):
    claim = detail(client, "RB-00006")
    use_model(
        app,
        fake_model(answer(group_sum_krw=claim["group_sum_krw"])),
    )
    assert client.post("/api/claims/RB-00006/review").status_code == 200
    approve = {"decision": "승인", "reason": "", **SUPPORT}
    assert client.post("/api/claims/RB-00006/decision", json=approve).is_success
    rec = detail(client, "RB-00006")["ai_review"]
    assert (rec["human_decision"], rec["agreed"]) == ("승인", True)


def test_review_conflicts_are_409_and_missing_is_404(app, client):
    use_model(app, None)
    assert client.post("/api/claims/RB-00054/review").status_code == 200
    again = client.post("/api/claims/RB-00120/review")
    assert again.status_code == 409
    assert "이미 사람 결정을 기다리고" in again.json()["detail"]
    paid = client.post("/api/claims/RB-00049/review")
    assert paid.status_code == 409
    assert client.post("/api/claims/RB-99999/review").status_code == 404


def test_no_model_review_is_fallback(app, client):
    use_model(app, None)
    body = client.post("/api/claims/RB-00006/review").json()
    assert body["fallback_used"] is True
    assert body["recommendation"] is None


def test_detail_without_review_has_no_ai_review(client):
    assert detail(client, "RB-00006")["ai_review"] is None
