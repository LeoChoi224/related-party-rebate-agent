"""장려금 건 API.

처리함 목록(13), 건 상세(14), 대상월 접수, 전결 건 결정, 지급 지시(11), AI 검토(17)가 있다.
전결 결정은 09 서비스가 권한 · 상태를 검사하고 바꾼 뒤에만 기다리는 AI 검토를 재개한다.
권한 부족(403) · 상태 전이 오류(409)는 main.py 의 처리기가 바꾸고, 요청 트랜잭션은 롤백된다.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from app.agents.graphs.claim_review import record_human_decision, start_claim_review
from app.api.deps import ReviewModelDep, SessionDep
from app.models import Agency, RebateClaim, RelatedGroup
from app.models.enums import ClaimStatus
from app.schemas.ai_recommendation import AiReviewOut
from app.schemas.approval import ClaimDecisionResult, DecisionRequest
from app.schemas.payment import PaymentOrderRequest, PaymentOrderResult
from app.schemas.rebate import ClaimDetail, ClaimListItem, IntakeResult
from app.services.approval import decide_claim
from app.services.claim_detail import TARGET_CLAIM, get_claim_detail
from app.services.intake import intake_period
from app.services.payment import order_payment

router = APIRouter(prefix="/claims", tags=["claims"])

# 연도 4자리-01~12월. 2026-6 · 2026-13 · 202606 은 422 가 된다.
PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


# 접두사 /claims 자체가 목록 주소다. "/" 로 두면 /api/claims 가 307 로 한 번 더 돈다.
@router.get("")
def list_claims(
    session: SessionDep,
    # list 인자는 Query() 가 없으면 요청 본문으로 읽힌다. ?status=전결대기&status=상신대기
    status: Annotated[
        list[ClaimStatus] | None,
        Query(description="거를 상태(여러 개 가능). 비우면 전체"),
    ] = None,
) -> list[ClaimListItem]:
    """처리함 목록. 고른 상태의 건을 건 ID 순으로 돌려준다."""
    query = (
        select(RebateClaim, Agency.agency_name, RelatedGroup.label)
        .join(Agency, RebateClaim.agency_id == Agency.agency_id)
        # 단독 대리점은 group_id 가 비어 있다. 그냥 join 이면 그 건이 목록에서 빠진다.
        .outerjoin(RelatedGroup, RebateClaim.group_id == RelatedGroup.group_id)
        .order_by(RebateClaim.rebate_id)
    )
    if status:
        query = query.where(RebateClaim.status.in_(status))
    return [
        ClaimListItem(
            rebate_id=claim.rebate_id,
            agency_id=claim.agency_id,
            agency_name=agency_name,
            period_ym=claim.period_ym,
            rebate_amount_krw=claim.rebate_amount_krw,
            status=claim.status,
            min_authority=claim.min_authority,
            group_label=group_label,
            group_sum_krw=claim.group_sum_krw,
        )
        for claim, agency_name, group_label in session.execute(query).all()
    ]


@router.get("/{rebate_id}", responses={404: {"description": "장려금 건이 없음"}})
def get_claim(rebate_id: str, session: SessionDep) -> ClaimDetail:
    """건 상세: 원본 기록, 결재 경로 판정과 근거, 승인 요청, 지급, 이력."""
    try:
        return get_claim_detail(session, rebate_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


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
    rebate_id: str, body: DecisionRequest, request: Request, session: SessionDep
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
    # 검사를 통과한 결정만 그래프에 넣는다(403 · 409 면 여기까지 오지 않는다).
    record_human_decision(
        session,
        request.app.state.checkpointer,
        TARGET_CLAIM,
        rebate_id,
        decision=body.decision,
        reason=body.reason,
        actor=body.actor,
    )
    return ClaimDecisionResult(rebate_id=claim.rebate_id, status=claim.status)


@router.post(
    "/{rebate_id}/review",
    responses={
        404: {"description": "장려금 건이 없음"},
        409: {"description": "결정 대기 건이 아니거나, 이미 검토해 결정을 기다림"},
    },
)
def review(
    rebate_id: str, request: Request, session: SessionDep, model: ReviewModelDep
) -> AiReviewOut:
    """AI 검토를 사람 결정 앞까지 돌린다. 상신 건은 승인 요청 단위로 한 번만 검토한다."""
    try:
        rec = start_claim_review(
            session, request.app.state.checkpointer, model, rebate_id
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return AiReviewOut.model_validate(rec)


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
