"""FastAPI 앱 진입점.

API 라우터를 /api 아래에 등록하고, React 빌드 결과(frontend/dist)가 있으면
같은 서버에서 함께 내보낸다. 화면 주소(/claims/RB-00006 등)로 바로 들어와도
index.html 을 돌려줘서 React 가 주소를 보고 화면을 고르게 한다.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.api.router import api_router
from app.core.config import FRONTEND_DIST


def create_app(frontend_dist: Path = FRONTEND_DIST) -> FastAPI:
    app = FastAPI(title="W07 판매장려금 통제 데스크")
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
