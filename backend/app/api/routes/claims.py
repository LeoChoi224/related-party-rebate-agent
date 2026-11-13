"""장려금 건 API.

대상월 접수, 전결 건 결정, 지급 지시(11)가 있다. 처리함 목록 · 건 상세는 13 · 14 에서 더한다.
권한 부족(403) · 상태 전이 오류(409)는 main.py 의 처리기가 바꾸고, 요청 트랜잭션은 롤백된다.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import SessionDep
from app.models import RebateClaim
from app.schemas.approval import ClaimDecisionResult, DecisionRequest
from app.schemas.payment import PaymentOrderRequest, PaymentOrderResult
from app.schemas.rebate import IntakeResult
from app.services.approval import decide_claim
from app.services.intake import intake_period
from app.services.payment import order_payment

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


@router.post(
    "/{rebate_id}/decision",
    responses={
        403: {"description": "결정하는 역할이 이 건의 최소 결재권자보다 낮음"},
        404: {"description": "장려금 건이 없음"},
        409: {"description": "전결대기 건이 아님(상신 건은 승인 요청으로 결정)"},
    },
)
def decide(
    rebate_id: str, body: DecisionRequest, session: SessionDep
) -> ClaimDecisionResult:
    """전결대기 건 하나를 승인 또는 반려한다. 반려는 사유가 필요하다."""
    try:
        claim = decide_claim(
            session,
            rebate_id,
            decision=body.decision,
            reason=body.reason,
            actor=body.actor,
            role=body.role,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return ClaimDecisionResult(rebate_id=claim.rebate_id, status=claim.status)


@router.post(
    "/{rebate_id}/payment-order",
    responses={
        403: {"description": "재무가 아님"},
        404: {"description": "장려금 건이 없음"},
        409: {"description": "승인 건도, 계좌오류로 보류된 건도 아님"},
    },
)
def order(
    rebate_id: str, body: PaymentOrderRequest, session: SessionDep
) -> PaymentOrderResult:
    """재무가 지급을 지시한다. 건은 지급지시가 되고 은행 회신 [모의] 을 기다린다."""
    try:
        payment = order_payment(session, rebate_id, actor=body.actor, role=body.role)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return PaymentOrderResult(
        payment_id=payment.payment_id,
        rebate_id=payment.rebate_id,
        amount_krw=payment.amount_krw,
        status=payment.status,
        # 같은 세션이라 전이가 끝난 건 객체가 그대로 돌아온다.
        claim_status=session.get(RebateClaim, rebate_id).status,
    )
