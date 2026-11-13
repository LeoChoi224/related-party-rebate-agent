"""시작 시 초기화와 초기화 API 테스트. 모두 임시 DB 엔진을 넣어 실제 app.db 를 건드리지 않는다."""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.database import make_engine
from app.main import create_app
from app.models import RebateClaim

EXPECTED_COUNTS = {
    "agency": 50,
    "ar_item": 146,
    "deposit": 32,
    "rebate_claim": 240,
    "identity_attr": 182,
    "group_version": 1,
    "related_group": 1,
    "group_member": 3,
    "relation_edge": 4,
    "event_log": 0,
    "approval_request": 0,
    "approval_item": 0,
    "task": 0,
    "ai_recommendation": 0,
    "payment_order": 0,
    "bank_reply": 0,
    "explanation_request": 0,
    "explanation_reply": 0,
    "explanation_check": 0,
    "master_change": 0,
}


@pytest.fixture
def empty_engine(tmp_path):
    """표가 하나도 없는 임시 파일 DB."""
    eng = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    yield eng
    eng.dispose()


@pytest.fixture
def client(tmp_path, empty_engine):
    """with 로 열어 lifespan(시작 시 초기화)까지 실행한 클라이언트."""
    app = create_app(tmp_path / "missing", engine=empty_engine)
    with TestClient(app) as c:
        yield c


def count_by_status(engine, status: str) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).where(RebateClaim.status == status))


def test_startup_fills_empty_database(client, empty_engine):
    """빈 DB 로 켜도 시작하면서 원본 240건이 채워진다."""
    assert count_by_status(empty_engine, "미접수") == 40
    assert count_by_status(empty_engine, "지급완료") == 196


def test_reset_endpoint_returns_row_counts(client):
    """POST /api/demo/reset 은 표 이름별 행 수를 돌려준다."""
    res = client.post("/api/demo/reset")
    assert res.status_code == 200
    assert res.json() == {"counts": EXPECTED_COUNTS}


def test_reset_endpoint_restores_changed_state(client, empty_engine):
    """시연 중 바뀐 상태가 초기화 뒤 원본 첫 값으로 돌아온다."""
    with Session(empty_engine) as session, session.begin():
        session.execute(
            update(RebateClaim)
            .where(RebateClaim.status == "미접수")
            .values(status="반려")
        )
    assert count_by_status(empty_engine, "미접수") == 0

    assert client.post("/api/demo/reset").status_code == 200
    assert count_by_status(empty_engine, "미접수") == 40
    assert count_by_status(empty_engine, "반려") == 4


def test_reset_requires_post(client):
    """초기화는 상태를 바꾸므로 GET 으로는 실행되지 않는다."""
    assert client.get("/api/demo/reset").status_code == 405


def test_only_app_loggers_show_info(client):
    """app 로거의 INFO 는 보이고, 다른 라이브러리(httpx)의 INFO 는 섞이지 않는다."""
    assert logging.getLogger("app.seed.seeder").isEnabledFor(logging.INFO)
    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
