"""상계 API(필수 확장) [가정]: 영업 의견(23), AI 상계액 추천, 재무 결정, 대리점 동의 [모의].

상계 제안은 관련자 그룹 건이 승인될 때 결정 API 가 만든다(claims · approvals 라우터).
조회는 건 상세(GET /claims/{id})의 offsets 칸에서 한다.
권한 부족(403) · 상태 충돌(409)은 main.py 의 처리기가 바꾸고, 요청 트랜잭션은 롤백된다.
"""

from fastapi import APIRouter, HTTPException

from app.api.deps import ReviewModelDep, SessionDep
from app.schemas.offset import (
    AgencyConsentRequest,
    OffsetDecisionRequest,
    OffsetOut,
    OffsetResult,
    SalesOpinionRequest,
)
from app.services.offset import (
    InvalidOffsetError,
    apply_agency_consent,
    decide_offset,
    offset_out,
    payable_krw,
    recommend_offset,
    submit_sales_opinion,
)

router = APIRouter(prefix="/offsets", tags=["offsets"])


def _result(session, proposal, claim) -> OffsetResult:
    return OffsetResult(
        offset=offset_out(session, proposal),
        claim_status=claim.status,
        payable_krw=payable_krw(session, claim),
    )


@router.post(
    "/{offset_id}/sales-opinion",
    responses={
        403: {"description": "영업지원팀 · 영업임원이 아님"},
        404: {"description": "상계 제안이 없음"},
        409: {"description": "재무가 이미 결정한 제안"},
        422: {"description": "부분 상계액이 없거나 한도 밖, 의견이 비어 있음"},
    },
)
def sales_opinion(
    offset_id: int, body: SalesOpinionRequest, session: SessionDep
) -> OffsetOut:
    """영업이 대리점 관계 부담을 보고 대안(전액 · 부분 상계 · 지급 후 회수 약정)을 낸다."""
    try:
        proposal = submit_sales_opinion(
            session,
            offset_id,
            alternative=body.alternative,
            amount_krw=body.amount_krw,
            opinion=body.opinion,
            actor=body.actor,
            role=body.role,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except InvalidOffsetError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return offset_out(session, proposal)


@router.post(
    "/{offset_id}/recommend",
    responses={
        404: {"description": "상계 제안이 없음"},
        409: {"description": "재무가 이미 결정한 제안"},
    },
)
def recommend(offset_id: int, session: SessionDep, model: ReviewModelDep) -> OffsetOut:
    """AI 상계액 추천을 받는다. 모델이 없거나 2회 실패하면 대체 모드로 기록한다."""
    try:
        proposal = recommend_offset(session, offset_id, model)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return offset_out(session, proposal)


@router.post(
    "/{offset_id}/decision",
    responses={
        403: {"description": "재무가 아님"},
        404: {"description": "상계 제안이 없음"},
        409: {"description": "이미 재무가 결정한 제안"},
        422: {"description": "상계액이 1~상계 한도 밖이거나, 반려 사유가 없음"},
    },
)
def decide(
    offset_id: int, body: OffsetDecisionRequest, session: SessionDep
) -> OffsetResult:
    """재무가 상계액을 정하거나(대리점 동의 대기) 상계하지 않기로 한다(전액 지급)."""
    try:
        proposal, claim = decide_offset(
            session,
            offset_id,
            decision=body.decision,
            amount_krw=body.offset_amount_krw,
            reason=body.reason,
            actor=body.actor,
            role=body.role,
            collection_due_date=body.collection_due_date,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except InvalidOffsetError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return _result(session, proposal, claim)


@router.post(
    "/{offset_id}/agency-consent",
    responses={
        404: {"description": "상계 제안이 없음"},
        409: {
            "description": "대리점 동의를 기다리는 제안이 아니거나, 연체 잔액이 모자람"
        },
    },
)
def agency_consent(
    offset_id: int, body: AgencyConsentRequest, session: SessionDep
) -> OffsetResult:
    """대리점 회신 [모의] 을 넣는다. 동의면 채권 잔액을 줄이고, 전액 상계면 건이 상계완료가 된다."""
    try:
        proposal, claim = apply_agency_consent(session, offset_id, body.consent)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _result(session, proposal, claim)
