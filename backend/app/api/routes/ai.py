"""AI 추천 기록 API(25): 세 AI 의 출력 · 사람 결정 · 일치율. 읽기만 한다."""

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.schemas.ai_recommendation import AiLogOut
from app.services.ai_log import ai_log

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/recommendations")
def recommendations(session: SessionDep) -> AiLogOut:
    """장려금 검토 · 소명 검토 · 상계 추천의 기록(최신순)과 종류별 일치율."""
    return ai_log(session)
