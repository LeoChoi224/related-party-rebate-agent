"""소명 API 테스트: 반려 건 소명 요청 → 모의 회신 → AI 검토 → 영업지원팀 확인.

모델 의존성을 가짜 모델로 바꿔 진짜 키 · 네트워크 없이 시나리오 3 을 API 끝까지 본다.
"""

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.agents.tools import collect_refs, find_agencies_by_account
from app.api.deps import get_review_model
from app.core.database import make_engine
from app.main import create_app

EXECUTIVE = {"actor": "박임원", "role": "영업임원"}
SUPPORT = {"actor": "김지원", "role": "영업지원팀"}
FINANCE = {"actor": "이재무", "role": "재무"}
G1_ACCOUNT = "국민 412-27-556310"
REPLY = "D-024는 별도 법인이고, 계좌가 겹친 건 세무대리인이 대신 입금해서입니다."


@pytest.fixture
def api_engine(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    yield eng
    eng.dispose()


@pytest.fixture
def app(tmp_path, api_engine):
    app = create_app(tmp_path / "missing", engine=api_engine)
    # 진짜 키가 있는 환경에서도 테스트가 외부 모델을 부르지 않게, 기본은 모델 없음(대체 모드)이다.
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


def reject_g1(client) -> str:
    """영업임원이 G1 승인 요청을 반려한다. 포함 3건이 모두 반려가 된다. 건 하나의 ID 를 돌려준다."""
    request_id = detail(client, "RB-00054")["approval"]["request_id"]
    body = {"decision": "반려", "reason": "소명 먼저", **EXECUTIVE}
    assert client.post(f"/api/approvals/{request_id}/decision", json=body).is_success
    return "RB-00054"


def reject_standalone(client) -> str:
    body = {"decision": "반려", "reason": "증빙 확인", **SUPPORT}
    assert client.post("/api/claims/RB-00006/decision", json=body).is_success
    return "RB-00006"


def request_explanation(client, rebate_id, **body):
    payload = {"requested_items": ["계좌 공유 사유"], **SUPPORT} | body
    return client.post(f"/api/claims/{rebate_id}/explanation-requests", json=payload)


def reply_to(client, exp_id, text=REPLY):
    return client.post(
        f"/api/explanation-requests/{exp_id}/reply", json={"raw_text": text}
    )


def mismatch_model(fake_explanation_model, api_engine):
    from sqlalchemy.orm import Session

    with Session(api_engine) as session:
        ref = min(collect_refs(find_agencies_by_account(session, G1_ACCOUNT)))
    return fake_explanation_model(
        {
            "ExtractedClaims": [{"claims": ["세무대리인이 대신 입금했다"]}],
            "CheckResult": [
                {
                    "verdict": "불일치",
                    "finding": "그 계좌는 D-011 · D-037 등록계좌",
                    "evidence_refs": [ref],
                }
            ],
            "ExplanationAssessment": [
                {
                    "judgement": "증빙 부족",
                    "rationale": ["입금 계좌가 G1 공유계좌"],
                    "missing_evidence": ["입금 대행 계약서"],
                    "follow_up_request": "입금 대행 계약서를 보내 주세요",
                    "confidence": 0.8,
                }
            ],
        },
        tool_turns=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "find_agencies_by_account",
                        "args": {"account": G1_ACCOUNT},
                        "id": "call_1",
                    }
                ],
            )
        ],
    )


def test_scenario_three_end_to_end(app, client, api_engine, fake_explanation_model):
    """임원 반려 → 소명 요청 → 모의 회신 → AI 가 불일치를 찾음 → 영업지원팀 확인 → 지급보류."""
    rebate_id = reject_g1(client)
    assert detail(client, rebate_id)["status"] == "반려"

    created = request_explanation(client, rebate_id)
    assert created.status_code == 200, created.text
    exp = created.json()
    assert (exp["status"], exp["reply"]) == ("회신대기", None)
    assert detail(client, rebate_id)["status"] == "소명대기"
    tasks = client.get("/api/tasks", params={"dept": "영업지원팀"}).json()
    assert any(
        t["task_type"] == "소명 요청" and t["ref_id"] == rebate_id for t in tasks
    )

    app.dependency_overrides[get_review_model] = lambda: mismatch_model(
        fake_explanation_model, api_engine
    )
    replied = reply_to(client, exp["exp_id"]).json()
    assert replied["status"] == "회신됨"
    assert replied["reply"]["provenance"] == "모의"
    # 회신을 등록하는 순간 AI 검토가 돌아 주장별 대조 결과가 이미 저장되어 있다(21).
    reply = replied["reply"]
    assert reply["ai_judgement"] == "증빙 부족"
    assert [c["verdict"] for c in reply["checks"]] == ["불일치"]

    decision = {"judgement": "증빙 부족", "reason": "계좌가 G1 공유계좌", **SUPPORT}
    done = client.post(f"/api/explanations/{reply['reply_id']}/decision", json=decision)
    assert done.status_code == 200, done.text
    assert done.json() == {
        "reply_id": reply["reply_id"],
        "judgement": "증빙 부족",
        "claim_status": "지급보류",
    }

    body = detail(client, rebate_id)
    assert body["status"] == "지급보류"
    (final,) = body["explanations"]
    assert final["status"] == "확인완료"
    assert final["reply"]["review_result"] == "증빙 부족"
    assert final["reply"]["agreed"] is True
    assert final["reply"]["reviewed_by"] == "김지원"
    assert final["reply"]["reviewed_at"].endswith("Z")
    tasks = client.get("/api/tasks", params={"dept": "영업지원팀"}).json()
    assert any(t["task_type"] == "추가 소명 요청" for t in tasks)


def test_sufficient_confirmation_resubmits_to_approval_path_without_ai(client):
    """AI 검토를 한 번도 안 돌려도 영업지원팀이 확인할 수 있다. 비교할 AI 판단이 없어 agreed 는 비어 있다."""
    rebate_id = reject_standalone(client)
    exp = request_explanation(client, rebate_id).json()
    reply_id = reply_to(client, exp["exp_id"]).json()["reply"]["reply_id"]

    done = client.post(
        f"/api/explanations/{reply_id}/decision",
        json={"judgement": "증빙 충분", **SUPPORT},
    )
    assert done.status_code == 200
    body = detail(client, rebate_id)
    # 증빙 충분이면 관계확인을 거쳐 바로 다시 판정되어 결재 경로로 돌아간다(재상신, 21).
    assert body["status"] == "전결대기"
    assert body["explanations"][0]["reply"]["agreed"] is None
    assert [e["to_status"] for e in body["events"]][-3:] == [
        "소명대기",
        "관계확인",
        "전결대기",
    ]
    assert body["events"][-2]["reason"] == "소명 확인: 증빙 충분"


def test_no_model_review_is_fallback_with_original_text(client):
    rebate_id = reject_standalone(client)
    exp = request_explanation(client, rebate_id).json()
    # 모델이 없어도 회신을 등록하면 AI 검토가 대체 모드로 끝난다(21).
    body = reply_to(client, exp["exp_id"]).json()
    assert body["reply"]["fallback_used"] is True
    assert body["reply"]["ai_judgement"] is None
    assert body["reply"]["raw_text"] == REPLY


def test_request_permissions_and_state_rules(client):
    standalone = "RB-00006"
    # 결재 대기 건(전결대기)은 소명을 요청할 수 없다.
    assert request_explanation(client, standalone).status_code == 409
    # 상신대기 G1 건도 마찬가지다: 승인 요청이 3건을 한 묶음으로 쥐고 있다.
    assert request_explanation(client, "RB-00054").status_code == 409
    rebate_id = reject_standalone(client)
    assert request_explanation(client, rebate_id, **FINANCE).status_code == 403
    assert request_explanation(client, "RB-99999").status_code == 404
    assert request_explanation(client, rebate_id, requested_items=[]).status_code == 422
    assert (
        request_explanation(client, rebate_id, requested_items=["  "]).status_code
        == 422
    )
    assert request_explanation(client, rebate_id, **EXECUTIVE).status_code == 200
    # 진행 중인 요청이 있으면 또 만들 수 없다.
    assert request_explanation(client, rebate_id).status_code == 409


def test_reply_rules(client):
    rebate_id = reject_standalone(client)
    exp_id = request_explanation(client, rebate_id).json()["exp_id"]
    assert reply_to(client, 9999).status_code == 404
    assert reply_to(client, exp_id, text="   ").status_code == 422
    assert reply_to(client, exp_id).status_code == 200
    again = reply_to(client, exp_id)
    assert again.status_code == 409 and "회신대기" in again.json()["detail"]


def test_confirmation_rules(client):
    rebate_id = reject_standalone(client)
    exp_id = request_explanation(client, rebate_id).json()["exp_id"]
    unreplied = client.post(
        "/api/explanations/1/decision", json={"judgement": "증빙 충분", **SUPPORT}
    )
    assert unreplied.status_code == 404
    reply_id = reply_to(client, exp_id).json()["reply"]["reply_id"]
    url = f"/api/explanations/{reply_id}/decision"

    assert (
        client.post(url, json={"judgement": "증빙 충분", **EXECUTIVE}).status_code
        == 403
    )
    assert (
        client.post(url, json={"judgement": "증빙 부족", **SUPPORT}).status_code == 422
    )
    # 403 · 422 뒤에도 건은 그대로 소명대기이고 요청은 아직 확인 전이다.
    assert detail(client, rebate_id)["status"] == "소명대기"
    assert (
        client.post(url, json={"judgement": "증빙 충분", **SUPPORT}).status_code == 200
    )
    again = client.post(url, json={"judgement": "증빙 충분", **SUPPORT})
    assert again.status_code == 409


def test_review_conflicts(app, client, api_engine, fake_explanation_model):
    rebate_id = reject_standalone(client)
    exp_id = request_explanation(client, rebate_id).json()["exp_id"]
    # 회신 전에는 검토할 수 없다.
    assert client.post("/api/explanations/1/review").status_code == 404
    reply_id = reply_to(client, exp_id).json()["reply"]["reply_id"]
    # 회신을 등록할 때 이미 검토해 확인을 기다리므로 다시 시작할 수 없다(21).
    again = client.post(f"/api/explanations/{reply_id}/review")
    assert again.status_code == 409
    assert "이미 사람 결정을 기다리고" in again.json()["detail"]


def test_second_round_after_hold_creates_new_request(client):
    """지급보류 뒤 추가 소명: 새 요청 · 새 회신으로 한 번 더 돈다. 이전 기록은 그대로 남는다."""
    rebate_id = reject_standalone(client)
    first = request_explanation(client, rebate_id).json()["exp_id"]
    reply_id = reply_to(client, first).json()["reply"]["reply_id"]
    hold = {"judgement": "증빙 부족", "reason": "계약서 없음", **SUPPORT}
    assert client.post(f"/api/explanations/{reply_id}/decision", json=hold).is_success
    assert detail(client, rebate_id)["status"] == "지급보류"

    second = request_explanation(
        client, rebate_id, requested_items=["입금 대행 계약서"]
    )
    assert second.status_code == 200
    assert second.json()["exp_id"] != first
    assert [e["status"] for e in detail(client, rebate_id)["explanations"]] == [
        "확인완료",
        "회신대기",
    ]
    assert detail(client, rebate_id)["status"] == "소명대기"
