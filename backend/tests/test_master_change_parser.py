"""정정 신고 문장 해석(19, master_change_parser) 테스트.

신고 문장 → AI 해석(가짜 모델) → 가드 → 영업지원팀 확인 → 20 의 정정 적용. 진짜 키 없이 본다.
D-041 주소를 D-034 와 같은 "대전시 중앙로 260" 으로 바꾸면 새 그룹 G2 가 생기고 6월분 2건이 다시 판정된다(20).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.guards import check_master_change_parse
from app.api.deps import get_review_model
from app.core.database import make_engine
from app.main import create_app
from app.models import MasterChange
from app.schemas.master_change import MasterChangeParse

SUPPORT = {"actor": "김지원", "role": "영업지원팀"}
SENTENCE = "D-041 대리점입니다. 본사를 대전시 중앙로 260 으로 이전했습니다."
D034_ADDRESS = "대전시 중앙로 260"


def parse_answer(**overrides) -> dict:
    values = {
        "agency_id": "D-041",
        "attr_type": "주소",
        "new_value": D034_ADDRESS,
        "effective_date": None,
        "confidence": 0.9,
    }
    return values | overrides


# ---------------------------------------------------------------- 가드


@pytest.mark.parametrize(
    ("raw_text", "answer", "problem"),
    [
        (SENTENCE, parse_answer(), None),
        # 문장에 ID 가 없어도 이름이 있으면 된다.
        ("미래상사41 본사가 대전시 중앙로 260 으로 옮겼습니다", parse_answer(), None),
        # 띄어쓰기만 다르면 같은 값이다.
        (SENTENCE, parse_answer(new_value="대전시 중앙로260"), None),
        (SENTENCE, parse_answer(agency_id="D-999"), "없는 대리점"),
        (SENTENCE, parse_answer(agency_id="D-034"), "문장에 D-034"),
        (SENTENCE, parse_answer(new_value="대전시 중앙로 261"), "문장에 없습니다"),
        (SENTENCE, parse_answer(new_value="서울시 옛주소 1"), "문장에 없습니다"),
        (SENTENCE, parse_answer(confidence=1.2), "확신도"),
    ],
)
def test_parse_guard(raw_text, answer, problem):
    """있는 대리점 · 문장 속 대리점과 값 · 확신도 범위를 본다. AI 가 지어낸 값은 문제로 잡힌다."""
    result = check_master_change_parse(
        MasterChangeParse.model_validate(answer),
        raw_text=raw_text,
        agency_names={"D-034": "대전상사34", "D-041": "미래상사41"},
        current_values={("D-041", "주소"): "서울시 옛주소 1"},
    )
    if problem is None:
        assert result.ok, result.problems
    else:
        assert any(problem in p for p in result.problems), result.problems


def test_guard_rejects_value_that_is_already_current():
    result = check_master_change_parse(
        MasterChangeParse.model_validate(parse_answer()),
        raw_text=SENTENCE,
        agency_names={"D-041": "미래상사41"},
        current_values={("D-041", "주소"): D034_ADDRESS},
    )
    assert result.problems == [f"D-041 의 주소 는 이미 '{D034_ADDRESS}' 입니다"]


# ---------------------------------------------------------------- API


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


def use_model(app, model):
    app.dependency_overrides[get_review_model] = lambda: model


def create(client, text=SENTENCE, **who):
    return client.post(
        "/api/master-change-reports", json={"raw_text": text, **(who or SUPPORT)}
    )


def apply(client, report_id, reason="", **fields):
    body = {
        "apply": True,
        "agency_id": "D-041",
        "attr_type": "주소",
        "new_value": D034_ADDRESS,
        "effective_date": None,
        "reason": reason,
        **SUPPORT,
    } | fields
    return client.post(f"/api/master-change-reports/{report_id}/decision", json=body)


def change_count(engine) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(MasterChange))


def test_parse_then_apply_same_values_regroups(app, client, fake_model, engine):
    """해석이 가드를 통과해 저장되고, 같은 값으로 적용하면 G2 가 생겨 2건이 다시 판정되고 일치로 남는다."""
    use_model(app, fake_model(parse_answer()))
    res = create(client)
    assert res.status_code == 200
    report = res.json()
    assert (
        report["status"],
        report["ai_agency_id"],
        report["ai_attr_type"],
        report["ai_new_value"],
        report["verified"],
        report["provenance"],
    ) == ("확인대기", "D-041", "주소", D034_ADDRESS, True, "주장")
    assert report["created_at"].endswith("Z")

    res = apply(client, report["report_id"])
    assert res.status_code == 200
    body = res.json()
    assert (body["report"]["status"], body["report"]["agreed"]) == ("적용", True)
    assert body["result"]["group_retained"] is False
    assert len(body["result"]["claims"]) == 2
    change = client.get("/api/master-changes").json()[0]
    assert (change["change_id"], change["reported_text"]) == (
        body["report"]["change_id"],
        SENTENCE,
    )
    # 확인을 받아 그래프가 끝났으므로 두 번째 확인은 서비스가 409 로 막는다.
    assert apply(client, report["report_id"]).status_code == 409
    assert change_count(engine) == 1


def test_made_up_value_is_retried_once(app, client, fake_model):
    """문장에 없는 새 값을 내면 문제를 알려 한 번 더 묻고, 두 번째 답을 저장한다."""
    model = fake_model(parse_answer(new_value="대전시 중앙로 999"), parse_answer())
    use_model(app, model)
    report = create(client).json()
    assert (report["ai_new_value"], report["problems"]) == (D034_ADDRESS, [])
    assert len(model.calls) == 2
    assert "문장에 없습니다" in model.calls[1][-1][1]


def test_two_failures_fall_back_to_manual_input(app, client, fake_model):
    """2회 모두 가드에 걸리면 해석 없이 문제만 남기고, 사람이 폼에 넣은 값으로 적용한다(비교 없음)."""
    use_model(
        app,
        fake_model(parse_answer(agency_id="D-999"), RuntimeError("timeout")),
    )
    report = create(client).json()
    assert (report["fallback_used"], report["ai_agency_id"]) == (True, None)
    assert report["problems"] == ["AI 호출 실패"]
    res = apply(client, report["report_id"])
    assert res.status_code == 200 and res.json()["report"]["agreed"] is None


def test_no_model_is_fallback(client):
    report = create(client).json()
    assert (report["fallback_used"], report["problems"]) == (
        True,
        ["LLM 키가 없어 대체 모드"],
    )


def test_apply_different_values_needs_reason(app, client, fake_model, engine):
    """AI 해석과 다른 값으로 적용하면 사유가 있어야 한다(25). 422 면 정정이 적용되지 않는다."""
    use_model(app, fake_model(parse_answer()))
    report_id = create(client).json()["report_id"]
    other = {"attr_type": "대표자", "new_value": "김새대표"}

    res = apply(client, report_id, **other)
    assert res.status_code == 422
    assert res.json()["detail"].startswith(
        "AI 추천(D-041 주소 → 대전시 중앙로 260)과 다른 결정(D-041 대표자 → 김새대표)"
    )
    assert change_count(engine) == 0
    res = apply(client, report_id, reason="전화로 대표자 변경임을 확인", **other)
    assert res.status_code == 200 and res.json()["report"]["agreed"] is False


def test_dismiss_needs_reason_and_applies_nothing(app, client, fake_model, engine):
    use_model(app, fake_model(parse_answer()))
    report_id = create(client).json()["report_id"]
    url = f"/api/master-change-reports/{report_id}/decision"
    assert client.post(url, json={"apply": False, **SUPPORT}).status_code == 422
    res = client.post(url, json={"apply": False, "reason": "중복 신고", **SUPPORT})
    assert res.status_code == 200
    assert (res.json()["report"]["status"], res.json()["result"]) == ("기각", None)
    assert change_count(engine) == 0


def test_errors_and_ai_log(app, client, fake_model):
    """영업지원팀이 아니면 403, 없는 신고 404, 빈 문장 · 빠진 값 422. 확인 뒤에는 AI 기록에 남는다."""
    assert create(client, actor="이재무", role="재무").status_code == 403
    assert create(client, text="   ").status_code == 422
    assert apply(client, 99).status_code == 404

    use_model(app, fake_model(parse_answer()))
    report_id = create(client).json()["report_id"]
    assert apply(client, report_id, actor="박임원", role="영업임원").status_code == 403
    assert apply(client, report_id, new_value=" ").status_code == 422
    assert apply(client, report_id).status_code == 200

    log = client.get("/api/ai/recommendations").json()
    row = next(r for r in log["rows"] if r["kind"] == "정정 신고 해석")
    assert (row["ai_output"], row["human_decision"], row["agreed"]) == (
        "D-041 주소 → 대전시 중앙로 260",
        "D-041 주소 → 대전시 중앙로 260",
        True,
    )
    stats = {s["kind"]: s for s in log["stats"]}
    assert stats["정정 신고 해석"]["agreement_rate"] == 1.0
