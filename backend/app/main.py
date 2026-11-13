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

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import Engine

from app.agents.checkpointer import make_checkpointer
from app.agents.runner import InvalidRunStateError
from app.api.router import api_router
from app.core.config import FRONTEND_DIST
from app.core.database import engine as default_engine
from app.seed.seeder import reset_database
from app.services.ai_agreement import ReasonRequiredError
from app.services.approval import InsufficientAuthorityError
from app.services.claim_state import InvalidTransitionError


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


def invalid_transition_handler(
    request: Request, exc: InvalidTransitionError
) -> JSONResponse:
    """상태 전이표에 없는 전이는 요청이 지금 상태와 충돌한 것이라 409 로 돌려준다."""
    return JSONResponse(status_code=409, content={"detail": str(exc)})


def invalid_run_state_handler(
    request: Request, exc: InvalidRunStateError
) -> JSONResponse:
    """이미 검토해 결정을 기다리거나 검토할 결정이 없으면 지금 상태와 충돌한 것이라 409."""
    return JSONResponse(status_code=409, content={"detail": str(exc)})


def insufficient_authority_handler(
    request: Request, exc: InsufficientAuthorityError
) -> JSONResponse:
    """결정하는 역할이 결재권자보다 낮으면 403 으로 돌려준다."""
    return JSONResponse(status_code=403, content={"detail": str(exc)})


def reason_required_handler(request: Request, exc: ReasonRequiredError) -> JSONResponse:
    """AI 추천과 다른 결정에 사유가 없으면 입력이 모자란 것이라 422(25)."""
    return JSONResponse(status_code=422, content={"detail": str(exc)})


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
    # 그래프 진행 위치. 앱을 켤 때마다 비어서 시작한다(업무 DB 와 같이).
    app.state.checkpointer = make_checkpointer()
    # 전이 오류 409 · 권한 부족 403 은 여러 API 가 함께 내므로 라우트마다 잡지 않고 한 곳에 둔다.
    app.add_exception_handler(InvalidTransitionError, invalid_transition_handler)
    app.add_exception_handler(InvalidRunStateError, invalid_run_state_handler)
    app.add_exception_handler(
        InsufficientAuthorityError, insufficient_authority_handler
    )
    app.add_exception_handler(ReasonRequiredError, reason_required_handler)
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
