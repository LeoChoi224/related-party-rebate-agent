"""감사 API(24): 과거 지급 건 사후 검토 실행.

권한 부족(403)은 main.py 의 처리기가 바꾼다. 같은 건에 작업이 이미 있으면 다시 만들지 않아 여러 번 불러도 된다.
"""

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.schemas.audit import RetroReviewRequest, RetroReviewResult
from app.services.retro_review import run_retro_review

router = APIRouter(prefix="/audit", tags=["audit"])


@router.post(
    "/retro-review",
    responses={403: {"description": "내부감사가 아님"}},
)
def retro_review(body: RetroReviewRequest, session: SessionDep) -> RetroReviewResult:
    """원본 지급 건을 지금 그룹으로 다시 판정해, 결재 단계가 모자랐던 건마다 사후 검토 작업을 연다."""
    return run_retro_review(session, actor=body.actor, role=body.role)
