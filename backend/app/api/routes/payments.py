"""지급 API: 은행 회신 [모의] 반영.

은행 회신 결과는 시연 패널(26)이 골라 넣는다. 회신하는 쪽은 사람이 아니라 은행(모의)이라
처리자를 본문에 받지 않는다. 지급 지시는 건에 대한 행동이라 claims 라우터에 있다.
"""

from fastapi import APIRouter, HTTPException

from app.api.deps import SessionDep
from app.schemas.payment import BankReplyRequest, BankReplyResult
from app.services.payment import apply_bank_reply

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "/{payment_id}/bank-reply",
    responses={
        404: {"description": "지급 지시가 없음"},
        409: {"description": "이미 회신을 받은 지급 지시(전체 롤백)"},
    },
)
def bank_reply(
    payment_id: int, body: BankReplyRequest, session: SessionDep
) -> BankReplyResult:
    """은행 회신 [모의] 을 넣는다. 성공이면 지급완료, 계좌오류면 지급보류."""
    try:
        order, reply, claim = apply_bank_reply(session, payment_id, body.result)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return BankReplyResult(
        payment_id=order.payment_id,
        result=reply.result,
        provenance=reply.provenance,
        claim_status=claim.status,
    )
