"""소명 API: 소명 요청, 회신 등록 [모의], AI 검토, 영업지원팀 확인.

확인은 서비스가 권한 · 상태를 검사하고 상태를 바꾼 뒤에만 기다리는 AI 검토를 재개한다(17 과 같음).
권한 부족(403) · 상태 충돌(409)은 main.py 의 처리기가 바꾸고, 요청 트랜잭션은 롤백된다.
"""

from fastapi import APIRouter, HTTPException, Request

from app.agents.graphs.explanation_review import (
    record_human_confirmation,
    start_explanation_review,
)
from app.api.deps import ReviewModelDep, SessionDep
from app.models import ExplanationRequest
from app.schemas.explanation import (
    ExplanationConfirmRequest,
    ExplanationConfirmResult,
    ExplanationOut,
    ExplanationRequestCreate,
    ReplyCreate,
)
from app.services.explanation import (
    confirm_explanation,
    explanation_out,
    register_reply,
    request_explanation,
)

router = APIRouter(tags=["explanations"])


@router.post(
    "/claims/{rebate_id}/explanation-requests",
    responses={
        403: {"description": "영업지원팀 · 영업임원이 아님"},
        404: {"description": "장려금 건이 없음"},
        409: {"description": "반려 · 지급보류 건이 아니거나 진행 중인 요청이 있음"},
    },
)
def create_request(
    rebate_id: str, body: ExplanationRequestCreate, session: SessionDep
) -> ExplanationOut:
    """반려 · 지급보류 건에 소명을 요청한다. 건은 소명대기가 된다."""
    try:
        request = request_explanation(
            session,
            rebate_id,
            items=body.requested_items,
            actor=body.actor,
            role=body.role,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return explanation_out(session, request)


@router.post(
    "/explanation-requests/{exp_id}/reply",
    responses={
        404: {"description": "소명 요청이 없음"},
        409: {"description": "회신대기 요청이 아님"},
    },
)
def reply(exp_id: int, body: ReplyCreate, session: SessionDep) -> ExplanationOut:
    """대리점 회신 [모의] 을 등록한다. 실제 업무에서는 대리점이 보내는 회신이다."""
    try:
        register_reply(session, exp_id, body.raw_text)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return explanation_out(session, session.get(ExplanationRequest, exp_id))


@router.post(
    "/explanations/{reply_id}/review",
    responses={
        404: {"description": "소명 회신이 없음"},
        409: {"description": "확인 전 회신이 아니거나, 이미 검토해 확인을 기다림"},
    },
)
def review(
    reply_id: int, request: Request, session: SessionDep, model: ReviewModelDep
) -> ExplanationOut:
    """AI 검토를 사람 확인 앞까지 돌린다. 주장을 뽑아 데이터와 대조하고 증빙이 충분한지 판단한다."""
    try:
        row = start_explanation_review(
            session, request.app.state.checkpointer, model, reply_id
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return explanation_out(session, session.get(ExplanationRequest, row.exp_id))


@router.post(
    "/explanations/{reply_id}/decision",
    responses={
        403: {"description": "영업지원팀이 아님"},
        404: {"description": "소명 회신이 없음"},
        409: {"description": "확인 전 회신이 아니거나 건이 소명대기가 아님"},
    },
)
def confirm(
    reply_id: int,
    body: ExplanationConfirmRequest,
    request: Request,
    session: SessionDep,
) -> ExplanationConfirmResult:
    """영업지원팀이 소명을 확인한다. 증빙 부족은 사유가 필요하다."""
    try:
        _, claim = confirm_explanation(
            session,
            reply_id,
            judgement=body.judgement,
            reason=body.reason,
            actor=body.actor,
            role=body.role,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    # 검사를 통과한 확인만 그래프에 넣는다(403 · 409 면 여기까지 오지 않는다).
    record_human_confirmation(
        session,
        request.app.state.checkpointer,
        reply_id,
        judgement=body.judgement,
        reason=body.reason,
        actor=body.actor,
    )
    return ExplanationConfirmResult(
        reply_id=reply_id, judgement=body.judgement, claim_status=claim.status
    )
