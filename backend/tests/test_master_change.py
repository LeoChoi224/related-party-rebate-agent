"""마스터 정정 신고 테스트: 그룹 재계산(새 버전), 결론 유지, 영향 건 재판정, 승인 요청 · 소명 요청 취소, 권한.

원본 데이터의 실제 숫자로 본다.
- D-037 등록계좌를 바꿔도 실입금계좌(G1 공유계좌)가 남아 G1 이 유지된다.
- D-041 주소를 D-034 와 같게 정정하면 새 그룹 (D-034, D-041) 의 6월 합산 2,255,709원이 한도를 넘어 상신대기가 된다.
- D-037 대표자를 바꾸면 G1 이 (D-011, D-024) 로 줄고, 합산 2,562,561원은 여전히 상신 대상이다.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.database import make_engine
from app.main import create_app

SUPPORT = {"actor": "김지원", "role": "영업지원팀"}
EXECUTIVE = {"actor": "박임원", "role": "영업임원"}
G1 = ["D-011", "D-024", "D-037"]
G1_ACCOUNT = "국민 412-27-556310"
D034_ADDRESS = "대전시 중앙로 260"


@pytest.fixture
def api_engine(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    yield eng
    eng.dispose()


@pytest.fixture
def app(tmp_path, api_engine):
    return create_app(tmp_path / "missing", engine=api_engine)


@pytest.fixture
def fresh(app):
    """접수 전 클라이언트(정정만 본다)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client(fresh):
    """6월분 접수까지 마친 클라이언트."""
    assert fresh.post("/api/claims/intake", params={"period": "2026-06"}).is_success
    return fresh


def report(client, agency_id, attr_type, new_value, **extra):
    body = {"attr_type": attr_type, "new_value": new_value, **SUPPORT} | extra
    return client.post(f"/api/agencies/{agency_id}/master-changes", json=body)


def detail(client, rebate_id):
    return client.get(f"/api/claims/{rebate_id}").json()


def statuses(client, rebate_id) -> list[str]:
    return [e["to_status"] for e in detail(client, rebate_id)["events"]]


def test_account_change_keeps_group_and_shows_evidence(fresh, api_engine):
    """D-037 등록계좌 변경: 실입금계좌가 여전히 G1 공유계좌라 그룹이 유지되고 근거가 보인다."""
    res = report(
        fresh,
        "D-037",
        "등록계좌",
        "신한 123-45-678901",
        reported_text="정산 계좌를 신한은행으로 옮겼습니다",
    )
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["group_retained"] is True
    assert body["groups_before"] == body["groups_after"]
    assert body["groups_after"] == [{"label": "G1", "members": G1}]
    assert (body["version_no_before"], body["version_no_after"]) == (1, 2)
    assert body["affected_agencies"] == [] and body["claims"] == []

    change = body["change"]
    assert (change["old_value"], change["new_value"]) == (
        G1_ACCOUNT,
        "신한 123-45-678901",
    )
    assert change["provenance"] == "주장"
    assert change["reported_text"] == "정산 계좌를 신한은행으로 옮겼습니다"

    # 근거: D-011 – D-037 은 대표자 + 계좌(D-037 쪽은 입금 기록의 실입금계좌) 2개로 여전히 관련자다.
    edge = next(
        e
        for e in body["evidence"]
        if (e["agency_a"], e["agency_b"]) == ("D-011", "D-037")
    )
    assert edge["judgement"] == "관련자" and edge["match_count"] == 2
    account = next(m for m in edge["matched_attrs"] if m["attr"] == "계좌")
    assert account["value"] == G1_ACCOUNT
    assert account["refs_b"]
    assert all("fin_collection_history_cv.csv" in ref for ref in account["refs_b"])


def test_correction_closes_old_value_and_keeps_original_master(fresh, api_engine):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.models import Agency, GroupVersion, IdentityAttribute

    assert report(fresh, "D-037", "등록계좌", "신한 123-45-678901").is_success
    with Session(api_engine) as session:
        rows = session.scalars(
            select(IdentityAttribute).where(
                IdentityAttribute.agency_id == "D-037",
                IdentityAttribute.attr_type == "등록계좌",
            )
        ).all()
        old = next(r for r in rows if r.value == G1_ACCOUNT)
        new = next(r for r in rows if r.value == "신한 123-45-678901")
        assert old.valid_to is not None and old.valid_to == new.valid_from
        assert new.valid_to is None and new.provenance == "주장"
        assert new.source_ref.startswith("master_change:")
        # 원본 대리점 마스터는 덮어쓰지 않는다.
        assert session.get(Agency, "D-037").bank_account_no == G1_ACCOUNT
        versions = session.scalars(
            select(GroupVersion).order_by(GroupVersion.version_no)
        ).all()
        assert [(v.version_no, v.is_current) for v in versions] == [
            (1, False),
            (2, True),
        ]


def test_address_change_creates_new_group_and_reroutes_to_executive(client):
    """D-041 주소 → D-034 와 같게: 새 그룹 G2 의 6월 합산이 한도를 넘어 두 건이 상신대기가 된다."""
    res = report(client, "D-041", "주소", D034_ADDRESS)
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["group_retained"] is False
    assert body["groups_after"] == [
        {"label": "G1", "members": G1},
        {"label": "G2", "members": ["D-034", "D-041"]},
    ]
    assert body["affected_agencies"] == ["D-034", "D-041"]

    by_id = {c["rebate_id"]: c for c in body["claims"]}
    assert set(by_id) == {"RB-00168", "RB-00198"}
    for impact in by_id.values():
        assert (impact["from_status"], impact["to_status"]) == ("전결대기", "상신대기")
        assert impact["min_authority_before"] == "영업지원팀"
        assert impact["min_authority_after"] == "영업임원"
        assert impact["group_sum_after"] == 2_255_709
    assert by_id["RB-00168"]["group_sum_before"] == 1_353_657
    request_id = by_id["RB-00168"]["approval_request_id"]
    assert (
        request_id is not None
        and request_id == by_id["RB-00198"]["approval_request_id"]
    )

    # 이력에 재검토필요를 거친 흔적이 남고, 승인 요청에 두 건이 함께 올랐다.
    assert statuses(client, "RB-00168")[-3:] == ["재검토필요", "관계확인", "상신대기"]
    assert detail(client, "RB-00168")["approval"]["rebate_ids"] == [
        "RB-00168",
        "RB-00198",
    ]
    # 재검토필요가 만든 재판정 작업은 바로 다시 판정되며 완료로 닫힌다.
    done = client.get("/api/tasks", params={"status": "완료"}).json()
    assert {t["ref_id"] for t in done if t["task_type"] == "재판정"} == {
        "RB-00168",
        "RB-00198",
    }
    # 정정과 무관한 G1 건은 그대로다.
    assert detail(client, "RB-00054")["status"] == "상신대기"
    assert detail(client, "RB-00054")["approval"]["request_id"] == 1


def test_splitting_group_cancels_old_request_and_makes_new_one(client):
    """D-037 대표자 변경으로 G1 이 (D-011, D-024) 로 줄면, 열려 있던 G1 승인 요청은 취소되고 새 요청이 생긴다."""
    assert detail(client, "RB-00054")["approval"]["request_id"] == 1

    res = report(client, "D-037", "대표자", "김새대표")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["groups_after"] == [{"label": "G1", "members": ["D-011", "D-024"]}]
    assert body["affected_agencies"] == ["D-011", "D-024", "D-037"]

    by_id = {c["rebate_id"]: c for c in body["claims"]}
    assert set(by_id) == {"RB-00054", "RB-00120", "RB-00180"}
    for rebate_id in ("RB-00054", "RB-00120"):
        assert by_id[rebate_id]["to_status"] == "상신대기"
        assert by_id[rebate_id]["group_sum_after"] == 2_562_561
    assert (
        by_id["RB-00054"]["approval_request_id"]
        == by_id["RB-00120"]["approval_request_id"]
    )
    assert by_id["RB-00054"]["approval_request_id"] != 1
    # D-037 은 혼자가 되어 1,325,536원 — 한도 이하라 전결이다.
    alone = by_id["RB-00180"]
    assert (alone["to_status"], alone["min_authority_after"]) == (
        "전결대기",
        "영업지원팀",
    )
    assert (
        alone["group_sum_after"] == 1_325_536 and alone["approval_request_id"] is None
    )

    # 옛 요청 1번은 취소되어 더는 결정할 수 없다.
    stale = client.post(
        "/api/approvals/1/decision",
        json={"decision": "승인", "reason": "", **EXECUTIVE},
    )
    assert stale.status_code == 409 and "취소" in stale.json()["detail"]
    fresh_id = by_id["RB-00054"]["approval_request_id"]
    ok = client.post(
        f"/api/approvals/{fresh_id}/decision",
        json={"decision": "승인", "reason": "", **EXECUTIVE},
    )
    assert ok.status_code == 200
    assert detail(client, "RB-00054")["status"] == "승인"
    assert detail(client, "RB-00180")["status"] == "전결대기"


def test_approved_claim_goes_back_to_review_and_is_rejudged_by_hand(client):
    """승인만 받은 건은 자동으로 되돌리지 않는다: 재검토필요로 두고 영업지원팀이 직접 재판정한다."""
    approve = {"decision": "승인", "reason": "", **SUPPORT}
    assert client.post("/api/claims/RB-00198/decision", json=approve).is_success
    assert detail(client, "RB-00198")["status"] == "승인"

    body = report(client, "D-041", "주소", D034_ADDRESS).json()
    by_id = {c["rebate_id"]: c for c in body["claims"]}
    # D-034 건은 결재 대기였으므로 바로 다시 판정된다. 합산에는 재검토필요인 D-041 건도 들어간다.
    assert by_id["RB-00168"]["to_status"] == "상신대기"
    assert by_id["RB-00168"]["group_sum_after"] == 2_255_709
    # D-041 건은 승인에서 재검토필요로만 돌아간다.
    held = by_id["RB-00198"]
    assert (held["from_status"], held["to_status"]) == ("승인", "재검토필요")
    assert held["min_authority_after"] is None and held["approval_request_id"] is None
    assert detail(client, "RB-00198")["status"] == "재검토필요"
    # 승인으로 열렸던 재무 지급 실행 작업은 건이 승인을 떠나며 닫혔다.
    open_tasks = client.get(
        "/api/tasks", params={"dept": "재무", "status": "열림"}
    ).json()
    assert not [t for t in open_tasks if t["ref_id"] == "RB-00198"]

    rejudged = client.post("/api/claims/RB-00198/rejudge", json=SUPPORT)
    assert rejudged.status_code == 200, rejudged.text
    result = rejudged.json()
    assert (result["status"], result["min_authority"]) == ("상신대기", "영업임원")
    assert result["group_sum_krw"] == 2_255_709
    # 같은 그룹 · 같은 달의 열린 승인 요청에 더해진다(요청이 둘로 갈라지지 않는다).
    assert result["approval_request_id"] == by_id["RB-00168"]["approval_request_id"]
    assert detail(client, "RB-00198")["approval"]["rebate_ids"] == [
        "RB-00168",
        "RB-00198",
    ]


def test_rejudge_rules(client):
    assert client.post("/api/claims/RB-00198/rejudge", json=SUPPORT).status_code == 409
    assert client.post("/api/claims/RB-99999/rejudge", json=SUPPORT).status_code == 404
    report(client, "D-041", "주소", D034_ADDRESS)
    client.post(
        "/api/claims/RB-00006/decision",
        json={"decision": "승인", "reason": "", **SUPPORT},
    )
    # 재검토필요 건이 아니면 영업임원이어도 먼저 권한을 본다.
    assert (
        client.post("/api/claims/RB-00006/rejudge", json=EXECUTIVE).status_code == 403
    )


def test_open_explanation_request_is_cancelled(client):
    """소명대기 중이던 건이 재검토필요로 돌아가면 받을 회신이 없으니 소명 요청도 취소된다."""
    reject = {"decision": "반려", "reason": "증빙 확인", **SUPPORT}
    assert client.post("/api/claims/RB-00198/decision", json=reject).is_success
    asked = client.post(
        "/api/claims/RB-00198/explanation-requests",
        json={"requested_items": ["주소 사유"], **SUPPORT},
    )
    assert (
        asked.status_code == 200 and detail(client, "RB-00198")["status"] == "소명대기"
    )

    assert report(client, "D-041", "주소", D034_ADDRESS).is_success
    body = detail(client, "RB-00198")
    assert body["status"] == "재검토필요"
    assert [e["status"] for e in body["explanations"]] == ["취소"]


def test_rejected_input_changes_nothing(fresh):
    cases = [
        (SUPPORT | {"role": "영업임원"}, "D-037", "대표자", "김새대표", 403),
        (SUPPORT, "D-999", "대표자", "김새대표", 404),
        (SUPPORT, "D-037", "대표자", "박상현", 422),  # 현재 값과 같음
        (SUPPORT, "D-037", "대표자", "   ", 422),  # 빈 값
        (
            SUPPORT,
            "D-037",
            "실입금계좌",
            "국민 111-11-111111",
            422,
        ),  # 입금 사실은 정정 대상이 아님
    ]
    for who, agency_id, attr_type, value, expected in cases:
        body = {"attr_type": attr_type, "new_value": value, **who}
        res = fresh.post(f"/api/agencies/{agency_id}/master-changes", json=body)
        assert res.status_code == expected, (agency_id, attr_type, res.text)
    early = report(fresh, "D-037", "대표자", "김새대표", effective_date="2001-01-01")
    assert early.status_code == 422 and "시작일" in early.json()["detail"]
    assert fresh.get("/api/master-changes").json() == []


def test_history_lists_newest_first_and_logs_event(fresh):
    assert report(fresh, "D-037", "등록계좌", "신한 123-45-678901").is_success
    assert report(fresh, "D-041", "주소", D034_ADDRESS).is_success
    changes = fresh.get("/api/master-changes").json()
    assert [(c["change_id"], c["agency_id"]) for c in changes] == [
        (2, "D-041"),
        (1, "D-037"),
    ]
    assert changes[0]["created_at"].endswith("Z")
    events = fresh.get("/api/events").json()
    logged = [e for e in events if e["entity_type"] == "master_change"]
    assert [e["entity_id"] for e in logged] == ["2", "1"]
    assert logged[1]["from_status"] == G1_ACCOUNT and logged[1]["actor"] == "김지원"
