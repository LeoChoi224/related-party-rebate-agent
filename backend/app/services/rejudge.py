"""재판정: 판정 단위가 바뀌었거나(정정 신고, 20) 소명으로 되살아난(21) 건을 지금 그룹으로 다시 판정해 결재 경로에 올린다.

AI 가 아니라 한도 판정 코드(06)의 계산이라 사람 결정을 대신하지 않는다. 결재는 올라간 뒤 사람이 한다.
commit 하지 않는다. 부르는 쪽 트랜잭션 안에서 다른 변경과 함께 확정 · 취소된다.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApprovalItem, ApprovalRequest, RebateClaim
from app.models.enums import ClaimStatus
from app.services.approval import open_approval_requests
from app.services.approval_authority import current_group_of, decide_authority
from app.services.claim_state import transition
from app.services.intake import NEXT_STATUS


def latest_request_id(session: Session, rebate_id: str) -> int | None:
    return session.scalar(
        select(ApprovalItem.request_id)
        .where(ApprovalItem.rebate_id == rebate_id)
        .order_by(ApprovalItem.request_id.desc())
        .limit(1)
    )


def rejudge_claims(
    session: Session,
    claims: list[RebateClaim],
    *,
    actor: str,
    role: str,
    reason: str,
) -> None:
    """재검토필요 또는 관계확인 건을 지금 버전 그룹으로 다시 판정해 결재 경로(전결대기 · 상신대기)에 올린다.

    한 달의 합산은 그 달의 모든 건(이미 지급된 건 포함)으로 계산하되, 판정 값은 넘겨받은 건에만 쓴다.
    다른 건의 판정 당시 값(그룹 · 합산)을 덮어쓰지 않기 위해서다.
    """
    for period in sorted({c.period_ym for c in claims}):
        period_claims = session.scalars(
            select(RebateClaim).where(RebateClaim.period_ym == period)
        ).all()
        decisions = {
            d.rebate_id: d
            for d in decide_authority(period_claims, current_group_of(session))
        }
        for claim in (c for c in claims if c.period_ym == period):
            decision = decisions[claim.rebate_id]
            claim.min_authority = decision.min_authority
            claim.group_id = decision.group_id
            claim.group_sum_krw = decision.group_sum_krw
            payload = {
                "group_id": decision.group_id,
                "group_sum_krw": decision.group_sum_krw,
                "min_authority": decision.min_authority,
            }
            # 소명 확인으로 이미 관계확인이 된 건은 그 단계를 다시 거치지 않는다.
            if claim.status != ClaimStatus.RELATION_CHECKED:
                transition(
                    session,
                    claim,
                    ClaimStatus.RELATION_CHECKED,
                    actor=actor,
                    actor_role=role,
                    reason=reason,
                    payload=payload,
                )
                payload = None
            transition(
                session,
                claim,
                NEXT_STATUS[decision.min_authority],
                actor=actor,
                actor_role=role,
                reason=(
                    f"판정 단위 합산 {decision.group_sum_krw:,}원 → "
                    f"최소 결재권자 {decision.min_authority}"
                ),
                payload=payload,
            )
    attach_or_open_requests(
        session, [c for c in claims if c.status == ClaimStatus.AWAITING_EXECUTIVE]
    )


def attach_or_open_requests(session: Session, claims: list[RebateClaim]) -> None:
    """상신대기가 된 건을 승인 요청에 올린다. 같은 그룹 · 같은 달의 열린 요청이 있으면 거기에 더한다."""
    fresh = []
    for claim in claims:
        request = (
            session.scalar(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.group_id == claim.group_id,
                    ApprovalRequest.period_ym == claim.period_ym,
                    ApprovalRequest.decision.is_(None),
                )
                .limit(1)
            )
            if claim.group_id is not None
            else None
        )
        if request is None:
            fresh.append(claim)
        else:
            session.add(
                ApprovalItem(request_id=request.request_id, rebate_id=claim.rebate_id)
            )
    if fresh:
        open_approval_requests(session, fresh)
    session.flush()
