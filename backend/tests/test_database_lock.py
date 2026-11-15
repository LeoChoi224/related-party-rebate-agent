"""SQLite 쓰기 잠금 대기(11/15 배포 앱 "database is locked") 테스트.

한 요청이 쓰기 잠금을 6초 잡고 있어도 다른 요청의 쓰기가 sqlite3 기본 대기 5초에 실패하지 않고,
잠금이 풀리면(LOCK_WAIT_SECONDS 안) 이어서 쓰는지 본다. 기본값 그대로면 이 테스트는 locked 로 실패한다.
"""

import threading
import time

from sqlalchemy import text

from app.core.database import LOCK_WAIT_SECONDS, make_engine

# sqlite3 기본 대기(5초)보다 길게 잡는다.
HOLD_SECONDS = 6


def test_second_writer_waits_for_lock_instead_of_failing(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'lock.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (v INTEGER)"))

    holder = engine.connect()
    holder.execute(
        text("BEGIN IMMEDIATE")
    )  # 쓰기 잠금을 잡는다(LLM 을 기다리는 요청처럼)
    holder.execute(text("INSERT INTO t VALUES (1)"))

    def release_later():
        time.sleep(HOLD_SECONDS)
        holder.commit()
        holder.close()

    threading.Thread(target=release_later).start()
    started = time.monotonic()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO t VALUES (2)"))
    waited = time.monotonic() - started

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM t")).scalar() == 2
    assert HOLD_SECONDS - 1 < waited < LOCK_WAIT_SECONDS
    engine.dispose()
