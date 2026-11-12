"""상신 API.

지금은 승인 요청 결정만 있다. 요청 상세 조회는 14 에서, AI 그래프 재개는 17 에서 더한다.
권한 부족(403) · 상태 전이 오류(409)는 main.py 의 처리기가 바꾸고, 요청 트랜잭션은 롤백된다.
"""

from fastapi import APIRouter, HTTPException

from app.api.deps import SessionDep
from app.schemas.approval import ApprovalDecisionResult, DecisionRequest
from app.services.approval import decide_approval

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
    request_id: int, body: DecisionRequest, session: SessionDep
) -> ApprovalDecisionResult:
    """승인 요청을 승인 또는 반려한다. 반려는 사유가 필요하다."""
    try:
        request, claims = decide_approval(
            session,
            request_id,
            decision=body.decision,
            reason=body.reason,
            actor=body.actor,
            role=body.role,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return ApprovalDecisionResult(
        request_id=request.request_id,
        decision=request.decision,
        decided_by=request.decided_by,
        rebate_ids=[c.rebate_id for c in claims],
    )
