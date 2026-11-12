"""SQLite 엔진.

업무 DB 는 앱을 켤 때마다 원본으로 다시 만든다(app/seed/seeder.py).
세션 팩토리와 요청마다 세션을 여는 의존성은 처음 조회 API 를 만드는 브랜치에서 추가한다.
"""

from sqlalchemy import Engine, create_engine, event

from app.core.config import DB_PATH


def make_engine(url: str) -> Engine:
    """외래키 검사를 켠 SQLite 엔진을 만든다. 테스트는 임시 파일 주소를 넘긴다."""
    # 파일 DB 면 SQLAlchemy 2.0 이 check_same_thread=False 를 알아서 넣는다.
    # 그래서 FastAPI 가 다른 스레드에서 연결을 다시 꺼내 써도 된다.
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        # SQLite 는 외래키 검사가 기본으로 꺼져 있고, 이 설정은 연결마다 따로다.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


DB_PATH.parent.mkdir(parents=True, exist_ok=True)
engine = make_engine(f"sqlite:///{DB_PATH}")
