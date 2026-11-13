"""API 라우터 묶음.

routes 아래 라우터를 모아 /api 접두사로 묶는다. 새 라우터는 여기에 한 줄씩 등록한다.
"""

from fastapi import APIRouter

from app.api.routes import (
    agencies,
    approvals,
    audit,
    claims,
    demo,
    events,
    explanations,
    health,
    offsets,
    payments,
    tasks,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(demo.router)
api_router.include_router(claims.router)
api_router.include_router(approvals.router)
api_router.include_router(tasks.router)
api_router.include_router(payments.router)
api_router.include_router(events.router)
api_router.include_router(explanations.router)
api_router.include_router(agencies.router)
api_router.include_router(offsets.router)
api_router.include_router(audit.router)
