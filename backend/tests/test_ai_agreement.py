"""AI 추천과 다르면 사유 필수 · AI 추천 기록(25) 테스트.

세 결정(전결 · 승인 요청, 소명 확인, 상계 재무 결정)에서 AI 와 다르게 고르면 사유가 없을 때 422 이고,
상태도 그래프도 바뀌지 않는다. 사유가 있으면 통과하고 불일치로 남는다. 대체 모드면 사유를 요구하지 않는다.
AI 기록 API 는 세 AI 의 출력 · 결정 · 일치율을 모은다. 가짜 모델로 진짜 키 없이 본다.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_review_model
from app.core.database import make_engine
from app.main import create_app
from app.models import ExplanationReply, OffsetProposal
from app.services.ai_agreement import (
    ReasonRequiredError,
    recommendation_matches,
    require_reason,
)

D001_JUNE = "RB-00006"  # 단독, 988,932원, 전결대기
G1_SUM = 3_888_097
SUPPORT = {"actor": "김지원", "role": "영업지원팀"}
EXECUTIVE = {"actor": "박임원", "role": "영업임원"}
FINANCE = {"actor": "이재무", "role": "재무"}


def assessment(recommendation: str, group_sum: int, authority: str) -> dict:
    return {
        "recommendation": recommendation,
        "ai_authority": authority,
        "group_sum_krw": group_sum,
        "rationale": ["근거 (sales_rebate_payment_cv.csv:7)"],
        "counter_evidence": [],
        "confidence": 0.8,
    }


@pytest.mark.parametrize(
    ("recommendation", "decision", "explained", "matches"),
    [
        ("승인", "승인", False, True),
        ("승인", "반려", False, False),
        ("반려", "반려", True, True),
        ("소명 먼저", "반려", True, True),
        ("소명 먼저", "반려", False, False),
        ("소명 먼저", "승인", False, False),
    ],
)
def test_recommendation_matches(recommendation, decision, explained, matches):
    """ "소명 먼저"는 반려하면서 소명을 요청했을 때만 같은 결정이다."""
    assert (
        recommendation_matches(recommendation, decision, explained=explained) is matches
    )


def test_require_reason_only_when_disagreeing_without_reason():
    require_reason(True, "", ai_output="승인", human="승인")
    require_reason(None, "", ai_output="", human="승인")  # 대체 모드
    require_reason(False, "현장 확인함", ai_output="반려", human="승인")
    with pytest.raises(
        ReasonRequiredError, match="AI 추천\\(반려\\)과 다른 결정\\(승인\\)"
    ):
        require_reason(False, "  ", ai_output="반려", human="승인")


@pytest.fixture
def app(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    app = create_app(tmp_path / "missing", engine=engine)
    app.dependency_overrides[get_review_model] = lambda: None
    app.state.test_engine = engine
    yield app
    engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        assert c.post("/api/claims/intake", params={"period": "2026-06"}).is_success
        yield c


def review(app, client, fake_model, rebate_id, answer):
    app.dependency_overrides[get_review_model] = lambda: fake_model(answer)
    assert client.post(f"/api/claims/{rebate_id}/review").is_success
    app.dependency_overrides[get_review_model] = lambda: None


def detail(client, rebate_id):
    return client.get(f"/api/claims/{rebate_id}").json()


def test_claim_decision_against_ai_needs_reason(app, client, fake_model):
    """AI 가 반려를 권한 건을 사유 없이 승인하면 422 이고 아무것도 바뀌지 않는다. 사유를 쓰면 불일치로 남는다."""
    review(
        app, client, fake_model, D001_JUNE, assessment("반려", 988_932, "영업지원팀")
    )
    url = f"/api/claims/{D001_JUNE}/decision"

    res = client.post(url, json={"decision": "승인", "reason": "", **SUPPORT})
    assert res.status_code == 422
    assert (
        res.json()["detail"]
        == "AI 추천(반려)과 다른 결정(승인)은 사유를 입력해야 합니다"
    )
    after = detail(client, D001_JUNE)
    assert (
        after["status"] == "전결대기" and after["ai_review"]["human_decision"] is None
    )

    res = client.post(
        url, json={"decision": "승인", "reason": "현장 실사로 확인", **SUPPORT}
    )
    assert res.status_code == 200
    rec = detail(client, D001_JUNE)["ai_review"]
    assert (rec["human_decision"], rec["agreed"], rec["human_reason"]) == (
        "승인",
        False,
        "현장 실사로 확인",
    )


def test_explain_first_matches_reject_with_explanation(app, client, fake_model):
    """AI 가 "소명 먼저"를 권하면 반려 + 소명 요청이 일치다."""
    review(
        app,
        client,
        fake_model,
        D001_JUNE,
        assessment("소명 먼저", 988_932, "영업지원팀"),
    )
    body = {
        "decision": "반려",
        "reason": "계좌 확인 필요",
        "explanation_items": ["계좌 사용 경위"],
        **SUPPORT,
    }
    assert client.post(f"/api/claims/{D001_JUNE}/decision", json=body).is_success
    assert detail(client, D001_JUNE)["ai_review"]["agreed"] is True


def test_approval_request_against_ai_needs_reason(app, client, fake_model):
    """G1 승인 요청도 같다. 422 면 3건 모두 상신대기로 남는다."""
    review(app, client, fake_model, "RB-00054", assessment("반려", G1_SUM, "영업임원"))
    res = client.post(
        "/api/approvals/1/decision",
        json={"decision": "승인", "reason": "", **EXECUTIVE},
    )
    assert res.status_code == 422
    assert {
        detail(client, r)["status"] for r in ("RB-00054", "RB-00120", "RB-00180")
    } == {"상신대기"}


def test_fallback_needs_no_reason(client):
    """AI 검토를 대체 모드로 돌렸으면 비교할 추천이 없어 사유 없이 결정된다."""
    assert (
        client.post(f"/api/claims/{D001_JUNE}/review").json()["fallback_used"] is True
    )
    res = client.post(
        f"/api/claims/{D001_JUNE}/decision",
        json={"decision": "승인", "reason": "", **SUPPORT},
    )
    assert res.status_code == 200
    assert detail(client, D001_JUNE)["ai_review"]["agreed"] is None


def test_explanation_confirm_against_ai_needs_reason(app, client):
    """AI 가 증빙 부족으로 본 회신을 사유 없이 증빙 충분으로 확인하면 422."""
    body = {
        "decision": "반려",
        "reason": "증빙 확인",
        "explanation_items": ["계좌"],
        **SUPPORT,
    }
    exp_id = client.post(f"/api/claims/{D001_JUNE}/decision", json=body).json()[
        "explanation_ids"
    ][0]
    reply_id = client.post(
        f"/api/explanation-requests/{exp_id}/reply",
        json={"raw_text": "정상 계좌입니다"},
    ).json()["reply"]["reply_id"]
    # 대체 모드로 돈 회신에 AI 판단을 직접 넣어 둔다(18 그래프 테스트가 판단 저장을 따로 본다).
    with Session(app.state.test_engine) as session, session.begin():
        reply = session.get(ExplanationReply, reply_id)
        reply.ai_judgement, reply.fallback_used, reply.verified = (
            "증빙 부족",
            False,
            True,
        )

    url = f"/api/explanations/{reply_id}/decision"
    res = client.post(url, json={"judgement": "증빙 충분", "reason": "", **SUPPORT})
    assert res.status_code == 422 and "AI 추천(증빙 부족)" in res.json()["detail"]
    assert detail(client, D001_JUNE)["status"] == "소명대기"
    res = client.post(
        url, json={"judgement": "증빙 충분", "reason": "통장 사본 확인", **SUPPORT}
    )
    assert res.status_code == 200


def test_offset_decision_against_ai_needs_reason(app, client, fake_model):
    """AI 가 1,000,000원 상계를 권했는데 재무가 한도 전액을 고르면 사유가 있어야 한다."""
    client.post(
        "/api/approvals/1/decision",
        json={"decision": "승인", "reason": "", **EXECUTIVE},
    )
    advice = {
        "offset_amount_krw": 1_000_000,
        "rationale": ["AR-D00092 164일 연체"],
        "counter_evidence": [],
        "confidence": 0.6,
    }
    app.dependency_overrides[get_review_model] = lambda: fake_model(advice)
    assert client.post("/api/offsets/1/recommend").json()["ai_amount_krw"] == 1_000_000

    body = {"decision": "승인", "offset_amount_krw": 1_373_515, "reason": "", **FINANCE}
    res = client.post("/api/offsets/1/decision", json=body)
    assert res.status_code == 422
    assert res.json()["detail"] == (
        "AI 추천(1,000,000원)과 다른 결정(1,373,515원)은 사유를 입력해야 합니다"
    )
    with Session(app.state.test_engine) as session:
        assert session.get(OffsetProposal, 1).status == "재무검토"
    body["reason"] = "연체 164일, 전액 회수 우선"
    assert client.post("/api/offsets/1/decision", json=body).is_success


def test_ai_log_collects_three_kinds_with_agreement_rate(app, client, fake_model):
    """장려금 검토 2건(일치 1 · 불일치 1), 상계 추천 1건(대체 모드)이 기록과 일치율에 그대로 나온다."""
    review(
        app, client, fake_model, D001_JUNE, assessment("승인", 988_932, "영업지원팀")
    )
    client.post(
        f"/api/claims/{D001_JUNE}/decision",
        json={"decision": "승인", "reason": "", **SUPPORT},
    )
    review(app, client, fake_model, "RB-00054", assessment("반려", G1_SUM, "영업임원"))
    client.post(
        "/api/approvals/1/decision",
        json={"decision": "승인", "reason": "관계 확인 끝", **EXECUTIVE},
    )
    client.post("/api/offsets/1/recommend")  # 모델 없음 → 대체 모드

    log = client.get("/api/ai/recommendations").json()
    stats = {s["kind"]: s for s in log["stats"]}
    assert (
        stats["장려금 검토"]["total"],
        stats["장려금 검토"]["compared"],
        stats["장려금 검토"]["agreed"],
        stats["장려금 검토"]["agreement_rate"],
    ) == (2, 2, 1, 0.5)
    assert (stats["상계 추천"]["total"], stats["상계 추천"]["fallback"]) == (1, 1)
    assert stats["상계 추천"]["agreement_rate"] is None
    assert stats["소명 검토"]["total"] == 0
    assert (stats["전체"]["compared"], stats["전체"]["agreement_rate"]) == (2, 0.5)

    rows = {r["target"]: r for r in log["rows"]}
    request_row = rows["approval_request:1"]
    assert (
        request_row["rebate_id"],
        request_row["agreed"],
        request_row["human_reason"],
    ) == (
        "RB-00054",
        False,
        "관계 확인 끝",
    )
    assert rows[f"rebate_claim:{D001_JUNE}"]["agreed"] is True
    assert rows["offset_proposal:1"]["ai_output"] is None
    assert log["rows"][0]["created_at"].endswith("Z")
