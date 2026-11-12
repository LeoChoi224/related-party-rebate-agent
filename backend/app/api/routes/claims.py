"""장려금 건 API.

지금은 대상월 접수만 있다. 처리함 목록 · 건 상세 · 전결 결정은 13 · 14 · 09 에서 더한다.
상태 전이 오류는 main.py 의 처리기가 409 로 바꾸고, 요청 트랜잭션은 롤백된다.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import SessionDep
from app.schemas.rebate import IntakeResult
from app.services.intake import intake_period

router = APIRouter(prefix="/claims", tags=["claims"])

# 연도 4자리-01~12월. 2026-6 · 2026-13 · 202606 은 422 가 된다.
PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


@router.post(
    "/intake",
    responses={
        404: {"description": "그 달의 장려금 건이 없음"},
        409: {"description": "이미 처리된 건이 있어 접수할 수 없음(전체 롤백)"},
    },
)
def intake(
    session: SessionDep,
    period: Annotated[
        str,
        Query(
            pattern=PERIOD_PATTERN, description="대상월(YYYY-MM)", examples=["2026-06"]
        ),
    ],
) -> IntakeResult:
    """대상월의 장려금 건을 모두 접수해 전결대기 · 상신대기로 보낸다."""
    try:
        by_status = intake_period(session, period)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return IntakeResult(
        period_ym=period, received=sum(by_status.values()), by_status=by_status
    )
