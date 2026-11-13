"""반려 → 소명 요청 → 회신 → AI 검토 → 확인 → 재상신 흐름 테스트(21).

- 반려 결정에 소명 항목을 함께 보내면 반려된 건마다 소명 요청이 생겨 건이 소명대기가 된다.
- 회신을 등록하면 AI 검토가 바로 돌고(모델이 없으면 대체 모드), 증빙 충분으로 확인하면
  건이 다시 판정되어 결재 경로로 돌아가며 AI 추천(claim_review)이 새로 붙는다.
- G1 은 건마다 소명을 받으므로, 먼저 확인된 건이 새 승인 요청을 열고 나중 건은 거기에 합류한다.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_review_model
from app.core.database import make_engine
from app.main import create_app

SUPPORT = {"actor": "김지원", "role": "영업지원팀"}
EXECUTIVE = {"actor": "박임원", "role": "영업임원"}
G1_CLAIMS = ["RB-00054", "RB-00120", "RB-00180"]
ITEMS = ["계좌 공유 사유"]


@pytest.fixture
def api_engine(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    yield eng
    eng.dispose()


@pytest.fixture
def app(tmp_path, api_engine):
    app = create_app(tmp_path / "missing", engine=api_engine)
    # 진짜 키가 있는 환경에서도 외부 모델을 부르지 않게, 기본은 모델 없음(대체 모드)이다.
    app.dependency_overrides[get_review_model] = lambda: None
    return app


@pytest.fixture
def client(app):
    """6월분 접수까지 마친 클라이언트."""
    with TestClient(app) as c:
        assert c.post("/api/claims/intake", params={"period": "2026-06"}).is_success
        yield c


def detail(client, rebate_id):
    return client.get(f"/api/claims/{rebate_id}").json()


def reject_g1(client, **extra):
    request_id = detail(client, "RB-00054")["approval"]["request_id"]
    body = {"decision": "반려", "reason": "소명 먼저", **EXECUTIVE} | extra
    return client.post(f"/api/approvals/{request_id}/decision", json=body)


def reply_and_confirm(client, rebate_id, judgement="증빙 충분", reason=""):
    """그 건의 소명 요청에 회신을 등록하고 영업지원팀이 확인한다. 확인 응답을 돌려준다."""
    exp = detail(client, rebate_id)["explanations"][-1]
    replied = client.post(
        f"/api/explanation-requests/{exp['exp_id']}/reply",
        json={"raw_text": "계좌는 정산 편의를 위한 공유였고 사업은 별개입니다."},
    )
    assert replied.status_code == 200, replied.text
    reply_id = replied.json()["reply"]["reply_id"]
    return client.post(
        f"/api/explanations/{reply_id}/decision",
        json={"judgement": judgement, "reason": reason, **SUPPORT},
    )


def test_executive_reject_with_items_asks_every_claim_in_the_unit(client):
    res = reject_g1(client, explanation_items=ITEMS)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["rebate_ids"] == G1_CLAIMS and len(body["explanation_ids"]) == 3

    for rebate_id in G1_CLAIMS:
        claim = detail(client, rebate_id)
        assert claim["status"] == "소명대기"
        (exp,) = claim["explanations"]
        assert (exp["status"], exp["requested_by"]) == ("회신대기", "박임원")
        assert exp["requested_items"] == ITEMS
    tasks = client.get("/api/tasks", params={"dept": "영업지원팀"}).json()
    asked = {t["ref_id"] for t in tasks if t["task_type"] == "소명 요청"}
    assert set(G1_CLAIMS) <= asked


def test_reject_without_items_is_unchanged(client):
    body = reject_g1(client).json()
    assert body["explanation_ids"] == []
    assert [detail(client, r)["status"] for r in G1_CLAIMS] == ["반려"] * 3
    assert detail(client, "RB-00054")["explanations"] == []


def test_support_reject_of_single_claim_can_ask_too(client):
    res = client.post(
        "/api/claims/RB-00006/decision",
        json={
            "decision": "반려",
            "reason": "증빙 확인",
            **SUPPORT,
            "explanation_items": ITEMS,
        },
    )
    assert res.status_code == 200 and len(res.json()["explanation_ids"]) == 1
    assert res.json()["status"] == "소명대기"
    assert detail(client, "RB-00006")["status"] == "소명대기"


@pytest.mark.parametrize(
    "body",
    [
        {"decision": "승인", "reason": "", "explanation_items": ITEMS},  # 반려가 아님
        {
            "decision": "반려",
            "reason": "소명 먼저",
            "explanation_items": ["  "],
        },  # 빈 항목
    ],
)
def test_explanation_items_validation(client, body):
    res = client.post("/api/claims/RB-00006/decision", json=body | SUPPORT)
    assert res.status_code == 422
    assert detail(client, "RB-00006")["status"] == "전결대기"


def test_sufficient_confirmation_resubmits_and_starts_claim_review(
    app, client, fake_explanation_model
):
    """반려 + 소명 요청 → 회신(AI 검토 자동) → 증빙 충분 확인 → 재판정 · 재상신 → AI 추천 → 결재."""
    client.post(
        "/api/claims/RB-00006/decision",
        json={
            "decision": "반려",
            "reason": "증빙 확인",
            **SUPPORT,
            "explanation_items": ITEMS,
        },
    )
    # 확인할 주장이 없는 회신이라 AI 는 증빙 부족으로 판단한다.
    insufficient = {
        "judgement": "증빙 부족",
        "rationale": ["확인할 주장이 없다"],
        "missing_evidence": ["계좌 공유 계약서"],
        "follow_up_request": "계좌 공유 계약서를 보내 주세요",
        "confidence": 0.5,
    }
    # 합산은 건마다 달라 하드코딩하지 않고 건 상세의 판정 값을 가짜 답에 넣는다.
    total = detail(client, "RB-00006")["group_sum_krw"]
    model = fake_explanation_model(
        {
            "ExtractedClaims": [{"claims": []}],
            "ExplanationAssessment": [insufficient],
            "ClaimAssessment": [
                {
                    "recommendation": "승인",
                    "ai_authority": "영업지원팀",
                    "group_sum_krw": total,
                    "rationale": ["소명 뒤 한도 이내"],
                    "counter_evidence": [],
                    "confidence": 0.8,
                }
            ],
        }
    )
    app.dependency_overrides[get_review_model] = lambda: model

    confirmed = reply_and_confirm(client, "RB-00006", reason="증빙 충분")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["claim_status"] == "전결대기"

    body = detail(client, "RB-00006")
    assert body["status"] == "전결대기"
    review = body["ai_review"]
    assert review["recommendation"] == "승인" and review["fallback_used"] is False
    assert review["target_type"] == "rebate_claim"
    # AI 는 증빙 부족이라 했지만 사람이 충분으로 확인했다 — 불일치가 기록된다.
    assert body["explanations"][0]["reply"]["agreed"] is False

    # 재상신된 건을 영업지원팀이 전결 승인하면 AI 추천과 일치로 기록된다.
    done = client.post(
        "/api/claims/RB-00006/decision",
        json={"decision": "승인", "reason": "", **SUPPORT},
    )
    assert done.status_code == 200
    final = detail(client, "RB-00006")
    assert (final["status"], final["ai_review"]["agreed"]) == ("승인", True)


def test_g1_claims_come_back_one_by_one_into_one_request(client):
    """G1 3건이 각자 소명을 받는다: 먼저 증빙 충분이 된 건이 새 승인 요청을 열고, 다음 건이 합류한다."""
    assert reject_g1(client, explanation_items=ITEMS).status_code == 200

    first = reply_and_confirm(client, "RB-00120", reason="계좌 공유 계약서 확인")
    assert first.status_code == 200 and first.json()["claim_status"] == "상신대기"
    opened = detail(client, "RB-00120")
    request = opened["approval"]
    assert request["request_id"] != 1
    assert request["rebate_ids"] == ["RB-00120"]
    # 나머지 두 건이 아직 소명대기여도 합산은 G1 전체(3건) 기준이라 영업임원 결재다.
    assert (request["approver_role"], request["group_sum_krw"]) == (
        "영업임원",
        3_888_097,
    )
    assert opened["min_authority"] == "영업임원"
    assert detail(client, "RB-00054")["status"] == "소명대기"

    second = reply_and_confirm(client, "RB-00054", reason="확인")
    assert second.status_code == 200 and second.json()["claim_status"] == "상신대기"
    joined = detail(client, "RB-00054")["approval"]
    assert joined["request_id"] == request["request_id"]
    assert joined["rebate_ids"] == ["RB-00054", "RB-00120"]

    # 세 번째는 증빙 부족 → 지급보류. 결재 요청에는 오르지 않는다.
    third = reply_and_confirm(
        client, "RB-00180", judgement="증빙 부족", reason="계약서 없음"
    )
    assert third.status_code == 200 and third.json()["claim_status"] == "지급보류"
    # 지급보류가 된 건은 새 승인 요청에 오르지 않고, 이전(반려된) 요청 1번만 남는다.
    assert detail(client, "RB-00180")["approval"]["request_id"] == 1

    approve = client.post(
        f"/api/approvals/{request['request_id']}/decision",
        json={"decision": "승인", "reason": "", **EXECUTIVE},
    )
    assert approve.status_code == 200
    # 승인된 두 건은 그룹 연체 채권 때문에 바로 상계검토로 넘어간다(22).
    assert [detail(client, r)["status"] for r in G1_CLAIMS] == [
        "상계검토",
        "상계검토",
        "지급보류",
    ]
