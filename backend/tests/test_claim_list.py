"""처리함 목록 API(GET /api/claims) 테스트.

원본으로 채운 앱에 6월분을 접수한 뒤, 상태 필터 · 그룹 라벨 · 합산 · 정렬 · 422 를 본다.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.database import make_engine
from app.main import create_app

G1 = {"D-011", "D-024", "D-037"}


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


def intake_june(client):
    res = client.post("/api/claims/intake", params={"period": "2026-06"})
    assert res.status_code == 200


def list_claims(client, *statuses):
    # params 에 리스트를 주면 ?status=A&status=B 처럼 같은 이름을 여러 번 붙인다.
    res = client.get("/api/claims", params={"status": list(statuses)})
    assert res.status_code == 200
    return res.json()


def test_inbox_is_empty_before_intake(client):
    """접수 전에는 전결대기 건이 없다. 6월분 40건은 아직 미접수다."""
    assert list_claims(client, "전결대기") == []
    not_received = list_claims(client, "미접수")
    assert len(not_received) == 40
    # 한도 판정 전이라 결재권자 · 합산이 비어 있다.
    assert {c["min_authority"] for c in not_received} == {None}
    assert {c["group_sum_krw"] for c in not_received} == {None}


def test_support_inbox_has_37_standalone_claims(client):
    """6월분 접수 뒤 영업지원팀 처리함: 전결대기 37건, 모두 단독 대리점."""
    intake_june(client)
    claims = list_claims(client, "전결대기")
    assert len(claims) == 37
    assert {c["min_authority"] for c in claims} == {"영업지원팀"}
    assert {c["group_label"] for c in claims} == {None}
    # 단독 대리점도 자기 금액이 판정 단위 합산이다.
    assert all(c["group_sum_krw"] == c["rebate_amount_krw"] for c in claims)


def test_executive_inbox_has_g1_with_group_sum(client):
    """영업임원 처리함: G1 3건, 그룹 합산 3,888,097원 → 영업임원."""
    intake_june(client)
    claims = list_claims(client, "상신대기")
    assert {c["agency_id"] for c in claims} == G1
    assert {c["group_label"] for c in claims} == {"G1"}
    assert {c["group_sum_krw"] for c in claims} == {3_888_097}
    assert {c["min_authority"] for c in claims} == {"영업임원"}
    assert sum(c["rebate_amount_krw"] for c in claims) == 3_888_097
    # 대리점 이름은 대리점 표에서 붙는다.
    assert all(c["agency_name"] for c in claims)


def test_two_statuses_are_combined_in_id_order(client):
    """상태를 둘 고르면 합쳐서 건 ID 순으로 돌려준다."""
    intake_june(client)
    claims = list_claims(client, "전결대기", "상신대기")
    ids = [c["rebate_id"] for c in claims]
    assert len(ids) == 40
    assert ids == sorted(ids)
    assert {c["period_ym"] for c in claims} == {"2026-06"}


def test_no_status_returns_all_240_claims(client):
    """상태를 비우면 전체 240건(지급완료 196 · 반려 4 · 미접수 40)."""
    claims = list_claims(client)
    assert len(claims) == 240
    by_status: dict[str, int] = {}
    for c in claims:
        by_status[c["status"]] = by_status.get(c["status"], 0) + 1
    assert by_status == {"지급완료": 196, "반려": 4, "미접수": 40}


def test_unknown_status_is_422(client):
    """없는 상태 값은 빈 목록이 아니라 422 다(오타와 '건 없음'을 구분)."""
    res = client.get("/api/claims", params={"status": "승인됨"})
    assert res.status_code == 422
