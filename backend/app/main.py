"""FastAPI 앱 진입점.

API 라우터를 /api 아래에 등록하고, React 빌드 결과(frontend/dist)가 있으면
같은 서버에서 함께 내보낸다. 화면 주소(/claims/RB-00006 등)로 바로 들어와도
index.html 을 돌려줘서 React 가 주소를 보고 화면을 고르게 한다.
켤 때마다 원본으로 업무 DB 를 다시 만든다.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import Engine

from app.api.router import api_router
from app.core.config import FRONTEND_DIST
from app.core.database import engine as default_engine
from app.seed.seeder import reset_database


def configure_app_logging() -> None:
    """app.* 로거의 INFO 를 터미널에 보이게 한다."""
    app_logger = logging.getLogger("app")
    # --reload 나 테스트로 여러 번 불려도 같은 줄이 두 번 찍히지 않게 한다.
    if app_logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s - %(message)s"))
    app_logger.addHandler(handler)
    # 루트 로거를 INFO 로 올리면 httpx 처럼 요청마다 INFO 를 남기는
    # 라이브러리 로그까지 섞인다. 우리 코드(app.*)만 연다.
    app_logger.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_app_logging()
    # 요청을 받기 전이라 동기 함수로 막아도 기다리는 요청이 없다.
    reset_database(app.state.engine)
    yield


def create_app(
    frontend_dist: Path = FRONTEND_DIST, engine: Engine = default_engine
) -> FastAPI:
    app = FastAPI(title="W07 판매장려금 통제 데스크", lifespan=lifespan)
    # 테스트는 임시 DB 엔진을 넣어 실제 app.db 를 건드리지 않는다.
    app.state.engine = engine
    app.include_router(api_router)

    # 개발 중에는 화면을 Vite(5173)가 내보내므로 dist 가 없어도 API 는 떠야 한다.
    if not frontend_dist.is_dir():
        return app

    dist_root = frontend_dist.resolve()
    index_file = dist_root / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str) -> FileResponse:
        # 없는 API 주소까지 index.html 로 돌려주면 화면에서 오류 원인을 못 찾는다.
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        file = (dist_root / full_path).resolve()
        # ../ 로 dist 밖의 파일을 읽지 못하게 막는다.
        if file.is_file() and file.is_relative_to(dist_root):
            return FileResponse(file)
        return FileResponse(index_file)

    return app


app = create_app()
