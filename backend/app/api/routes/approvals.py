"""상신 API.

지금은 승인 요청 결정만 있다. 요청 내용은 건 상세(14)의 승인 요청 칸에서 본다.
09 서비스가 권한 · 상태를 검사하고 바꾼 뒤에만 기다리는 AI 검토를 재개한다(17).
권한 부족(403) · 상태 전이 오류(409)는 main.py 의 처리기가 바꾸고, 요청 트랜잭션은 롤백된다.
"""

from fastapi import APIRouter, HTTPException, Request

from app.agents.graphs.claim_review import record_human_decision
from app.api.deps import SessionDep
from app.schemas.approval import ApprovalDecisionResult, DecisionRequest
from app.services.approval import decide_approval
from app.services.claim_detail import TARGET_REQUEST

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.post(
    "/{request_id}/decision",
    responses={
        403: {"description": "결정하는 역할이 요청의 결재권자보다 낮음"},
        404: {"description": "승인 요청이 없음"},
        409: {"description": "이미 결정된 요청(전체 롤백)"},
    },
)
def decide(
    request_id: int, body: DecisionRequest, request: Request, session: SessionDep
) -> ApprovalDecisionResult:
    """승인 요청을 승인 또는 반려한다. 반려는 사유가 필요하다."""
    try:
        approval, claims = decide_approval(
            session,
            request_id,
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
        TARGET_REQUEST,
        str(request_id),
        decision=body.decision,
        reason=body.reason,
        actor=body.actor,
    )
    return ApprovalDecisionResult(
        request_id=approval.request_id,
        decision=approval.decision,
        decided_by=approval.decided_by,
        rebate_ids=[c.rebate_id for c in claims],
    )
