"""SQLite 엔진 테스트: 외래키 검사, 스레드 간 연결 재사용, 기본 DB 경로."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import DB_PATH
from app.core.database import engine, make_engine


@pytest.fixture
def temp_engine(tmp_path):
    """실제 app.db 를 건드리지 않는 임시 파일 DB 엔진."""
    eng = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    yield eng
    eng.dispose()


def test_foreign_keys_on_for_every_connection(temp_engine):
    """동시에 연 두 연결 모두 외래키 검사가 켜져 있다."""
    with temp_engine.connect() as first, temp_engine.connect() as second:
        assert first.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert second.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_missing_parent_row_is_rejected(temp_engine):
    """없는 부모 행을 가리키는 외래키 값은 저장되지 않는다."""
    with temp_engine.begin() as conn:
        conn.execute(text("CREATE TABLE parent (id TEXT PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE child ("
                "id INTEGER PRIMARY KEY, parent_id TEXT REFERENCES parent(id))"
            )
        )
    with pytest.raises(IntegrityError), temp_engine.begin() as conn:
        conn.execute(text("INSERT INTO child (parent_id) VALUES ('D-999')"))


def test_pooled_connection_works_in_another_thread(temp_engine):
    """한 스레드에서 만든 연결을 다른 스레드가 다시 꺼내 써도 오류가 나지 않는다."""
    with temp_engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    def query_in_worker() -> int:
        with temp_engine.connect() as conn:
            return conn.execute(text("SELECT 1")).scalar()

    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(query_in_worker).result() == 1


def test_default_engine_uses_db_path():
    """기본 엔진은 config 의 DB_PATH 파일을 쓴다."""
    assert engine.url.database == str(DB_PATH)
    assert DB_PATH.parent.is_dir()
