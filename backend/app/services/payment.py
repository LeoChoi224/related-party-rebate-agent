"""지급 처리: 승인 · 상계검토 → 지급지시 → (은행 회신 [모의]) → 지급완료 또는 지급보류.

지급 지시는 재무만 낸다. 지급보류 건은 마지막 지시가 계좌오류였던 건만 다시 지시한다
(증빙 부족으로 보류된 건이 소명을 건너뛰고 지급되지 않게). 상계검토 건은 상계 제안이 끝난 뒤에만
(상계확정 · 재무반려 · 동의거절) 지시한다. 금액은 장려금액에서 확정된 상계액을 뺀 남은 금액(22).
회신 기록 · 지시 상태 · 건 상태는 요청 트랜잭션 하나에서 함께 바뀐다. commit 하지 않는다.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mocks.bank import BANK_ACTOR, BANK_ROLE, record_bank_reply
from app.models import BankReply, PaymentOrder, RebateClaim
from app.models.enums import BankResult, ClaimStatus, Department, PaymentStatus
from app.services.approval import InsufficientAuthorityError
from app.services.claim_state import InvalidTransitionError, transition
from app.services.offset import PAYABLE_AFTER, latest_offset, payable_krw

RESULT_TO_PAYMENT_STATUS = {
    BankResult.SUCCESS: PaymentStatus.SUCCEEDED,
    BankResult.ACCOUNT_ERROR: PaymentStatus.ACCOUNT_ERROR,
}
# 계좌오류면 10 의 규칙(지급지시 → 지급보류)으로 재무 "지급 계좌 확인" 작업이 열린다.
RESULT_TO_CLAIM_STATUS = {
    BankResult.SUCCESS: ClaimStatus.PAID,
    BankResult.ACCOUNT_ERROR: ClaimStatus.ON_HOLD,
}


def last_payment(session: Session, rebate_id: str) -> PaymentOrder | None:
    """그 건의 마지막 지급 지시. 시각은 초 단위라 겹칠 수 있어 payment_id 로 정한다."""
    return session.scalars(
        select(PaymentOrder)
        .where(PaymentOrder.rebate_id == rebate_id)
        .order_by(PaymentOrder.payment_id.desc())
        .limit(1)
    ).first()


def order_payment(
    session: Session, rebate_id: str, *, actor: str, role: str
) -> PaymentOrder:
    """재무가 지급을 지시한다. 건은 지급지시가 되고, 지급 실행 · 계좌 확인 작업이 닫힌다."""
    claim = session.get(RebateClaim, rebate_id)
    if claim is None:
        raise LookupError(f"장려금 건 {rebate_id} 이(가) 없습니다")
    # 전이표의 지급보류 → 지급지시 는 증빙 부족 보류와 계좌 오류 보류를 구별하지 못한다.
    # 지급 기록으로 계좌 오류였던 건만 다시 지시하게 한다.
    last = last_payment(session, rebate_id)
    retry = (
        claim.status == ClaimStatus.ON_HOLD
        and last is not None
        and last.status == PaymentStatus.ACCOUNT_ERROR
    )
    # 상계검토 → 지급지시(차액 · 전액 지급)는 제안이 결정 · 동의까지 끝났을 때만이다.
    if claim.status == ClaimStatus.OFFSET_REVIEW:
        offset = latest_offset(session, rebate_id)
        if offset is None or offset.status not in PAYABLE_AFTER:
            raise InvalidTransitionError(
                "상계 검토가 끝나지 않아 지급을 지시할 수 없습니다: "
                f"{offset.status if offset else '제안 없음'} ({rebate_id})"
            )
    elif claim.status != ClaimStatus.APPROVED and not retry:
        raise InvalidTransitionError(
            "지급 지시는 승인 · 상계검토 건이나 계좌오류로 보류된 건만 할 수 있습니다: "
            f"{claim.status} ({rebate_id})"
        )
    if role != Department.FINANCE:
        raise InsufficientAuthorityError(
            f"{role} 은(는) 지급을 지시할 수 없습니다. 재무만 지시합니다 ({rebate_id})"
        )

    order = PaymentOrder(
        rebate_id=rebate_id,
        amount_krw=payable_krw(session, claim),
        status=PaymentStatus.AWAITING_REPLY,
        ordered_by=actor,
    )
    session.add(order)
    session.flush()
    transition(
        session,
        claim,
        ClaimStatus.PAYMENT_ORDERED,
        actor=actor,
        actor_role=role,
        reason=f"지급 지시 {order.amount_krw:,}원",
        payload={"payment_id": order.payment_id},
    )
    return order


def apply_bank_reply(
    session: Session, payment_id: int, result: BankResult
) -> tuple[PaymentOrder, BankReply, RebateClaim]:
    """은행 회신 [모의] 을 반영한다. 성공이면 지급완료, 계좌오류면 지급보류."""
    order = session.get(PaymentOrder, payment_id)
    if order is None:
        raise LookupError(f"지급 지시 {payment_id} 이(가) 없습니다")
    # DB 유일 제약에만 맡기면 사용자는 409 대신 500 을 받는다. 먼저 알린다.
    if order.status != PaymentStatus.AWAITING_REPLY:
        raise InvalidTransitionError(
            f"이미 회신을 받은 지급 지시입니다: {order.status} (지급 {payment_id})"
        )

    reply = record_bank_reply(session, order, result)
    order.status = RESULT_TO_PAYMENT_STATUS[result]
    claim = session.get(RebateClaim, order.rebate_id)
    transition(
        session,
        claim,
        RESULT_TO_CLAIM_STATUS[result],
        actor=BANK_ACTOR,
        actor_role=BANK_ROLE,
        reason=f"은행 회신 {result} [모의]",
        payload={"payment_id": payment_id, "reply_id": reply.reply_id},
    )
    return order, reply, claim
