"""이벤트 이력 API(GET /api/events) 테스트.

원본으로 채운 앱에 6월분을 접수한 뒤, 최신순 · 건 · 처리자 역할 거르기 · 빈 결과 · 시각 표시를 본다.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.database import make_engine
from app.main import create_app

EXECUTIVE = {"actor": "박임원", "role": "영업임원"}


@pytest.fixture
def api_engine(tmp_path):
    """API 테스트용 빈 임시 DB. 앱이 켜지며 원본으로 채운다."""
    eng = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    yield eng
    eng.dispose()


@pytest.fixture
def client(tmp_path, api_engine):
    """6월분 접수까지 마친 클라이언트."""
    with TestClient(create_app(tmp_path / "missing", engine=api_engine)) as c:
        assert c.post("/api/claims/intake", params={"period": "2026-06"}).is_success
        yield c


def events(client, **params):
    res = client.get("/api/events", params=params)
    assert res.status_code == 200
    return res.json()


def test_events_are_newest_first(client):
    """접수 뒤 120줄(40건 × 3전이), 이력 번호가 큰 것부터."""
    rows = events(client)
    assert len(rows) == 120
    ids = [r["event_id"] for r in rows]
    assert ids == sorted(ids, reverse=True)
    assert rows[0]["ts"].endswith("Z")


def test_filter_by_claim(client):
    """건 ID 로 거르면 그 건의 3줄만, 어느 건인지 함께 실린다."""
    rows = events(client, rebate_id="RB-00054")
    assert [r["to_status"] for r in rows] == ["상신대기", "관계확인", "접수"]
    assert {(r["entity_type"], r["entity_id"]) for r in rows} == {
        ("rebate_claim", "RB-00054")
    }


def test_filter_by_actor_role(client):
    """접수는 모두 시스템이 한다. 영업임원이 결정하면 그 3줄이 위에 오고,
    그 위에 승인 직후 시스템이 상계검토로 넘긴 3줄이 온다(22)."""
    assert len(events(client, actor_role="시스템")) == 120
    assert events(client, actor_role="영업임원") == []

    approve = {"decision": "승인", "reason": "", **EXECUTIVE}
    assert client.post("/api/approvals/1/decision", json=approve).is_success

    rows = events(client, actor_role="영업임원")
    assert [r["entity_id"] for r in rows] == ["RB-00180", "RB-00120", "RB-00054"]
    newest = [(r["actor"], r["to_status"]) for r in events(client)[:4]]
    assert newest == [("시스템", "상계검토")] * 3 + [("박임원", "승인")]


def test_unknown_filters_are_empty_not_errors(client):
    """없는 건 · 없는 역할은 404 · 422 가 아니라 빈 목록이다."""
    assert events(client, rebate_id="RB-99999") == []
    assert events(client, actor_role="회계팀") == []
