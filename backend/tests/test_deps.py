"""요청 트랜잭션과 전이 오류 처리 테스트.

시험용 라우트를 임시 앱에 붙여, 정상이면 commit · 예외면 롤백되는지와
상태 전이 오류가 409 로 바뀌는지 본다. 모두 임시 DB 엔진을 쓴다.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SessionDep
from app.core.database import make_engine
from app.main import create_app
from app.models import RebateClaim
from app.models.enums import ClaimStatus
from app.services.claim_state import transition

# 원본 6월분 G1 의 D-011 건(미접수).
G1_JUNE = "RB-00054"


@pytest.fixture
def engine(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    yield eng
    eng.dispose()


@pytest.fixture
def client(tmp_path, engine):
    """시험용 라우트 3개를 붙이고 lifespan(시작 시 초기화)까지 돈 클라이언트."""
    app = create_app(tmp_path / "missing", engine=engine)

    def receive(session: SessionDep) -> RebateClaim:
        claim = session.get(RebateClaim, G1_JUNE)
        transition(
            session, claim, ClaimStatus.RECEIVED, actor="t", actor_role="t", reason="t"
        )
        return claim

    @app.post("/test/ok")
    def ok(session: SessionDep) -> dict:
        receive(session)
        return {"ok": True}

    @app.post("/test/error-after-change")
    def error_after_change(session: SessionDep) -> dict:
        receive(session)
        raise RuntimeError("바꾼 뒤에 터짐")

    @app.post("/test/invalid-transition")
    def invalid_transition(session: SessionDep) -> dict:
        claim = receive(session)
        # 접수 → 지급완료 는 전이표에 없다.
        transition(
            session, claim, ClaimStatus.PAID, actor="t", actor_role="t", reason="t"
        )
        return {"ok": True}

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def status_of(engine) -> str:
    with Session(engine) as session:
        return session.scalar(
            select(RebateClaim.status).where(RebateClaim.rebate_id == G1_JUNE)
        )


def test_normal_request_commits(client, engine):
    """정상으로 끝난 요청의 변경은 DB 에 남는다."""
    assert client.post("/test/ok").status_code == 200
    assert status_of(engine) == "접수"


def test_unexpected_error_rolls_back(client, engine):
    """바꾼 뒤에 예상 못 한 예외가 나면 500 이고 변경은 롤백된다."""
    assert client.post("/test/error-after-change").status_code == 500
    assert status_of(engine) == "미접수"


def test_invalid_transition_is_409_and_rolls_back(client, engine):
    """전이 오류는 409 와 한글 메시지로 바뀌고, 앞서 바꾼 접수도 롤백된다."""
    res = client.post("/test/invalid-transition")
    assert res.status_code == 409
    assert res.json() == {
        "detail": f"허용되지 않은 상태 전이입니다: 접수 → 지급완료 ({G1_JUNE})"
    }
    assert status_of(engine) == "미접수"
