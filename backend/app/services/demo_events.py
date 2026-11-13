"""시연 이벤트(26): 시나리오를 빨리 진행하려고 여러 건을 한 번에 처리한다.

새 업무 규칙은 없다. 사람이 화면에서 한 건씩 누르는 것과 같은 서비스(09 전결 결정 · 11 지급 지시 ·
11 은행 회신 [모의])를 같은 검사와 함께 차례로 부른다. 결정자는 그 일을 맡는 부서의 시연 인물이다.
한 요청 = 한 트랜잭션이라 중간에 한 건이라도 실패하면 전부 롤백된다. commit 하지 않는다.
"""

import logging

from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.graphs.claim_review import record_human_decision
from app.models import PaymentOrder, RebateClaim
from app.models.enums import BankResult, ClaimStatus, Decision, PaymentStatus
from app.schemas.demo import BankRepliesResult, StandaloneBatchResult
from app.services.ai_agreement import check_claim_decision
from app.services.approval import decide_claim
from app.services.claim_detail import TARGET_CLAIM
from app.services.payment import apply_bank_reply, order_payment

logger = logging.getLogger(__name__)

# 시연 인물. 화면 역할 목록(RoleContext)과 같은 이름이다.
SUPPORT = {"actor": "김지원", "role": "영업지원팀"}
FINANCE = {"actor": "이재무", "role": "재무"}
# AI 추천과 달라도 막히지 않게 사유를 늘 남긴다(25). 사유가 이력에 그대로 보여 시연 처리임이 드러난다.
BATCH_REASON = "시연 일괄 처리(시나리오 1)"


def approve_and_order_standalone(
    session: Session, checkpointer: BaseCheckpointSaver, period_ym: str
) -> StandaloneBatchResult:
    """대상월의 단독(그룹 없는) 전결대기 건을 영업지원팀이 전결 승인하고 재무가 지급 지시한다.

    그룹 건(G1 등)은 영업임원 결재 · 상계 검토를 직접 보여 줘야 해서 건드리지 않는다.
    """
    claims = session.scalars(
        select(RebateClaim)
        .where(
            RebateClaim.period_ym == period_ym,
            RebateClaim.status == ClaimStatus.AWAITING_SUPPORT,
            RebateClaim.group_id.is_(None),
        )
        .order_by(RebateClaim.rebate_id)
    ).all()
    payment_ids = []
    for claim in claims:
        decide_claim(
            session,
            claim.rebate_id,
            decision=Decision.APPROVE,
            reason=BATCH_REASON,
            **SUPPORT,
        )
        # 화면 결정과 같은 순서: 서비스 → 사유 검사 → 기다리는 AI 검토 재개(25 · 17).
        check_claim_decision(
            session,
            TARGET_CLAIM,
            claim.rebate_id,
            decision=Decision.APPROVE,
            reason=BATCH_REASON,
            explained=False,
        )
        record_human_decision(
            session,
            checkpointer,
            TARGET_CLAIM,
            claim.rebate_id,
            decision=Decision.APPROVE,
            reason=BATCH_REASON,
            actor=SUPPORT["actor"],
        )
        payment_ids.append(
            order_payment(session, claim.rebate_id, **FINANCE).payment_id
        )
    total = sum(c.rebate_amount_krw for c in claims)
    logger.info(
        "시연 일괄: %s 단독 %d건 전결 승인 · 지급 지시 %s원",
        period_ym,
        len(claims),
        f"{total:,}",
    )
    return StandaloneBatchResult(
        period_ym=period_ym,
        approved=len(claims),
        payment_ids=payment_ids,
        total_krw=total,
    )


def reply_all_payments(session: Session, result: BankResult) -> BankRepliesResult:
    """회신을 기다리는 지급 지시 전부에 같은 은행 회신 [모의] 을 넣는다."""
    orders = session.scalars(
        select(PaymentOrder)
        .where(PaymentOrder.status == PaymentStatus.AWAITING_REPLY)
        .order_by(PaymentOrder.payment_id)
    ).all()
    claim_status: dict[str, int] = {}
    for order in orders:
        _, _, claim = apply_bank_reply(session, order.payment_id, result)
        claim_status[claim.status] = claim_status.get(claim.status, 0) + 1
    logger.info("시연 은행 회신 [모의] %s: %d건", result, len(orders))
    return BankRepliesResult(
        result=result,
        replied=len(orders),
        total_krw=sum(o.amount_krw for o in orders),
        by_claim_status=claim_status,
    )
