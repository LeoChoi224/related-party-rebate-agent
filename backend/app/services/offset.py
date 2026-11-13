"""상계 검토(필수 확장) [가정]: 지급 전 같은 그룹의 연체 채권과 장려금을 상계한다.

흐름(모두 요청 트랜잭션 안, commit 하지 않는다):
1. 관련자 그룹 건이 승인되면(open_offset_reviews) 그룹 구성원의 90일 초과 연체 채권을 찾는다.
   남은 잔액이 있으면 상계 한도(코드)를 계산해 제안을 만들고 건을 승인 → 상계검토로 보낸다(재무 "상계 검토" 작업).
2. 재무가 AI 추천 [주장] 을 참고해 상계액을 정하거나(동의대기) 상계하지 않기로 한다(재무반려).
3. 대리점이 동의하면 [모의] 채권 잔액을 ARAdjustment 로 줄이고(원본 잔액은 그대로) 상계확정.
   장려금 전액을 상계했으면 건은 상계완료, 일부면 상계검토에 남아 재무가 차액을 지급 지시한다.
   대리점이 거절하거나 재무가 반려하면 재무가 전액을 지급 지시한다.

대상을 관련자 그룹 건으로 좁힌 것은 이 과제의 위험이 "관련 거래처가 장려금을 받으면서 채권은 연체"이기 때문이다.
단독 대리점의 연체는 재무의 일반 회수 업무로 두었다 [가정].
"""

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.agents.offset_advisor import advise_offset
from app.mocks.agency_reply import AGENCY_ACTOR, AGENCY_ROLE
from app.models import (
    Agency,
    ARAdjustment,
    ARItem,
    EventLog,
    GroupMember,
    OffsetProposal,
    RebateClaim,
    RelatedGroup,
)
from app.models.enums import (
    AgencyConsent,
    ClaimStatus,
    Decision,
    Department,
    OffsetStatus,
    Provenance,
)
from app.schemas.offset import ARAdjustmentOut, ARItemOut, OffsetOut
from app.services.approval import InsufficientAuthorityError
from app.services.claim_state import InvalidTransitionError, transition
from app.services.intake import SYSTEM_ACTOR

logger = logging.getLogger(__name__)

# 연체로 보는 기준 [가정]. 원본 aging_days 는 기준일(6/30) 현재 연체일이다.
OVERDUE_DAYS = 90
# 결정 · 동의를 기다리는 제안. 그룹 연체 잔액에서 이 제안들의 몫은 이미 잡힌 것으로 본다.
OPEN_OFFSET = (OffsetStatus.AWAITING_FINANCE, OffsetStatus.AWAITING_CONSENT)
# 이 상태로 끝난 제안이 있는 상계검토 건은 남은 금액을 지급 지시할 수 있다.
PAYABLE_AFTER = frozenset(
    {
        OffsetStatus.SETTLED,
        OffsetStatus.FINANCE_REJECTED,
        OffsetStatus.CONSENT_REFUSED,
    }
)


class InvalidOffsetError(ValueError):
    """상계 한도를 넘는 상계액 등 받을 수 없는 입력. API 는 422 로 돌려준다."""


def _members(session: Session, group_id: int) -> list[str]:
    return list(
        session.scalars(
            select(GroupMember.agency_id)
            .where(GroupMember.group_id == group_id)
            .order_by(GroupMember.agency_id)
        )
    )


def overdue_items(session: Session, group_id: int, own_agency: str) -> list[ARItemOut]:
    """그룹 구성원의 90일 초과 연체 채권과 지금 잔액. 상계 순서대로: 이 건의 대리점 먼저, 오래된 것 먼저."""
    adjusted = (
        select(ARAdjustment.ar_id, func.sum(ARAdjustment.amount_krw).label("done"))
        .group_by(ARAdjustment.ar_id)
        .subquery()
    )
    rows = session.execute(
        select(ARItem, func.coalesce(adjusted.c.done, 0))
        .outerjoin(adjusted, adjusted.c.ar_id == ARItem.ar_id)
        .where(
            ARItem.agency_id.in_(_members(session, group_id)),
            ARItem.aging_days > OVERDUE_DAYS,
        )
    ).all()
    items = [
        ARItemOut(
            ar_id=item.ar_id,
            agency_id=item.agency_id,
            due_date=item.due_date,
            aging_days=item.aging_days,
            outstanding_krw=item.outstanding_krw,
            remaining_krw=item.outstanding_krw - done,
            source_file=item.source_file,
            source_row=item.source_row,
        )
        for item, done in rows
    ]
    # 자기 채권 먼저: 다른 대리점 채권과의 상계는 그룹이라는 이유 하나로 넓힌 것이라 뒤에 둔다.
    return sorted(
        items, key=lambda i: (i.agency_id != own_agency, -i.aging_days, i.ar_id)
    )


def settled_offset_krw(session: Session, rebate_id: str) -> int:
    """이 건에서 대리점 동의까지 끝나 확정된 상계액 합계."""
    return session.scalar(
        select(func.coalesce(func.sum(OffsetProposal.offset_amount_krw), 0)).where(
            OffsetProposal.rebate_id == rebate_id,
            OffsetProposal.status == OffsetStatus.SETTLED,
        )
    )


def payable_krw(session: Session, claim: RebateClaim) -> int:
    """지금 지급할 금액 = 장려금액 - 확정된 상계액. 상계가 없으면 장려금액 그대로."""
    return claim.rebate_amount_krw - settled_offset_krw(session, claim.rebate_id)


def latest_offset(session: Session, rebate_id: str) -> OffsetProposal | None:
    """그 건의 마지막 상계 제안. 시각은 초 단위라 겹칠 수 있어 ID 로 정한다."""
    return session.scalars(
        select(OffsetProposal)
        .where(OffsetProposal.rebate_id == rebate_id)
        .order_by(OffsetProposal.offset_id.desc())
        .limit(1)
    ).first()


def open_offset_reviews(session: Session, claims: list[RebateClaim]) -> list[int]:
    """승인된 관련자 그룹 건마다 연체 채권을 보고, 상계할 잔액이 있으면 제안을 만들어 상계검토로 보낸다."""
    offset_ids = []
    for claim in claims:
        if claim.status != ClaimStatus.APPROVED or claim.group_id is None:
            continue
        items = [
            i
            for i in overdue_items(session, claim.group_id, claim.agency_id)
            if i.remaining_krw > 0
        ]
        total = sum(i.remaining_krw for i in items)
        # 같은 그룹의 다른 열린 제안이 잡아 둔 몫을 빼야 G1 3건이 같은 잔액을 두 번 쓰지 않는다.
        reserved = session.scalar(
            select(
                func.coalesce(
                    func.sum(
                        func.coalesce(
                            OffsetProposal.offset_amount_krw,
                            OffsetProposal.max_offset_krw,
                        )
                    ),
                    0,
                )
            ).where(
                OffsetProposal.group_id == claim.group_id,
                OffsetProposal.status.in_(OPEN_OFFSET),
            )
        )
        max_offset = min(payable_krw(session, claim), total - reserved)
        if max_offset <= 0:
            continue

        proposal = OffsetProposal(
            rebate_id=claim.rebate_id,
            group_id=claim.group_id,
            overdue_total_krw=total,
            max_offset_krw=max_offset,
            status=OffsetStatus.AWAITING_FINANCE,
        )
        session.add(proposal)
        session.flush()
        transition(
            session,
            claim,
            ClaimStatus.OFFSET_REVIEW,
            actor=SYSTEM_ACTOR,
            actor_role=SYSTEM_ACTOR,
            reason=(
                f"같은 그룹 {OVERDUE_DAYS}일 초과 연체 채권 {len(items)}건 "
                f"잔액 {total:,}원 — 상계 한도 {max_offset:,}원 [가정]"
            ),
            payload={"offset_id": proposal.offset_id},
        )
        offset_ids.append(proposal.offset_id)
    if offset_ids:
        logger.info("상계 검토 제안 %d건 생성: %s", len(offset_ids), offset_ids)
    return offset_ids


def _get(session: Session, offset_id: int) -> tuple[OffsetProposal, RebateClaim]:
    proposal = session.get(OffsetProposal, offset_id)
    if proposal is None:
        raise LookupError(f"상계 제안 {offset_id} 이(가) 없습니다")
    return proposal, session.get(RebateClaim, proposal.rebate_id)


def _log(
    session: Session,
    proposal: OffsetProposal,
    from_status: str,
    *,
    actor: str,
    role: str,
    reason: str,
) -> None:
    """제안 상태 변화를 이력에 남긴다. 건 상태 이력과 대상 종류로 나뉜다."""
    session.add(
        EventLog(
            actor=actor,
            actor_role=role,
            entity_type="offset_proposal",
            entity_id=str(proposal.offset_id),
            from_status=from_status,
            to_status=proposal.status,
            reason=reason,
            payload={"rebate_id": proposal.rebate_id},
        )
    )
    session.flush()


def _facts(
    session: Session, proposal: OffsetProposal, claim: RebateClaim
) -> dict[str, Any]:
    """프롬프트에 넣을 사실. 상계 한도는 코드 값이고 AI 는 그 안에서만 고른다."""
    agency = session.get(Agency, claim.agency_id)
    return {
        "건": {
            "건_ID": claim.rebate_id,
            "대리점": f"{agency.agency_id} {agency.agency_name}",
            "대상월": claim.period_ym,
            "장려금액_krw": claim.rebate_amount_krw,
            "근거_행": f"{claim.source_file}:{claim.source_row}",
        },
        "관련자_그룹": {
            "라벨": session.get(RelatedGroup, proposal.group_id).label,
            "구성원": _members(session, proposal.group_id),
        },
        "연체_기준_일": OVERDUE_DAYS,
        "연체_채권": [
            {
                "채권_ID": i.ar_id,
                "대리점": i.agency_id,
                "연체일": i.aging_days,
                "지금_잔액_krw": i.remaining_krw,
                "근거_행": f"{i.source_file}:{i.source_row}",
            }
            for i in overdue_items(session, proposal.group_id, claim.agency_id)
        ],
        "그룹_연체_잔액_krw": proposal.overdue_total_krw,
        "max_offset_krw": proposal.max_offset_krw,
    }


def recommend_offset(
    session: Session, offset_id: int, model: BaseChatModel | None
) -> OffsetProposal:
    """AI 상계액 추천을 받아 제안에 저장한다. 모델이 없거나 2회 실패하면 대체 모드로 기록한다."""
    proposal, claim = _get(session, offset_id)
    if proposal.status != OffsetStatus.AWAITING_FINANCE:
        raise InvalidTransitionError(
            f"재무 결정 전 제안만 AI 추천을 받을 수 있습니다: {proposal.status} "
            f"(상계 {offset_id})"
        )
    outcome = advise_offset(
        model, _facts(session, proposal, claim), max_offset_krw=proposal.max_offset_krw
    )
    advice = outcome.advice
    proposal.ai_amount_krw = advice.offset_amount_krw if advice else None
    proposal.ai_rationale = advice.rationale if advice else []
    proposal.ai_counter_evidence = advice.counter_evidence if advice else []
    proposal.ai_confidence = advice.confidence if advice else None
    proposal.verified = advice is not None
    proposal.fallback_used = advice is None
    proposal.model = getattr(model, "model_name", None) if advice else None
    session.flush()
    logger.info(
        "상계 #%d AI 추천: %s",
        offset_id,
        f"{advice.offset_amount_krw:,}원" if advice else "대체 모드",
    )
    return proposal


def decide_offset(
    session: Session,
    offset_id: int,
    *,
    decision: Decision,
    amount_krw: int | None,
    reason: str,
    actor: str,
    role: str,
) -> tuple[OffsetProposal, RebateClaim]:
    """재무가 상계액을 정하거나(대리점 동의 대기) 상계하지 않기로 한다(전액 지급)."""
    proposal, claim = _get(session, offset_id)
    if proposal.status != OffsetStatus.AWAITING_FINANCE:
        raise InvalidTransitionError(
            f"이미 재무가 결정한 상계 제안입니다: {proposal.status} (상계 {offset_id})"
        )
    if role != Department.FINANCE:
        raise InsufficientAuthorityError(
            f"{role} 은(는) 상계를 결정할 수 없습니다. 재무만 결정합니다 (상계 {offset_id})"
        )
    if decision == Decision.APPROVE and not (
        amount_krw is not None and 1 <= amount_krw <= proposal.max_offset_krw
    ):
        raise InvalidOffsetError(
            f"상계액 {amount_krw}원이 1~상계 한도 {proposal.max_offset_krw:,}원 밖입니다"
        )

    before = proposal.status
    approved = decision == Decision.APPROVE
    proposal.status = (
        OffsetStatus.AWAITING_CONSENT if approved else OffsetStatus.FINANCE_REJECTED
    )
    proposal.finance_decision = decision
    proposal.offset_amount_krw = amount_krw if approved else None
    proposal.finance_reason = reason.strip() or None
    proposal.decided_by = actor
    proposal.decided_at = func.now()
    # 상계하지 않기로 한 결정은 AI 가 0원을 권했을 때 일치다.
    if proposal.ai_amount_krw is not None:
        proposal.agreed = proposal.ai_amount_krw == (amount_krw if approved else 0)
    _log(
        session,
        proposal,
        before,
        actor=actor,
        role=role,
        reason=(
            f"상계 {amount_krw:,}원 승인 — 대리점 동의 요청"
            if approved
            else f"상계하지 않음 — {reason.strip()}"
        ),
    )
    return proposal, claim


def apply_agency_consent(
    session: Session, offset_id: int, consent: AgencyConsent
) -> tuple[OffsetProposal, RebateClaim]:
    """대리점 회신 [모의] 을 반영한다. 동의면 채권 잔액을 줄이고, 전액 상계면 건을 상계완료로 보낸다."""
    proposal, claim = _get(session, offset_id)
    if proposal.status != OffsetStatus.AWAITING_CONSENT:
        raise InvalidTransitionError(
            f"대리점 동의를 기다리는 상계 제안이 아닙니다: {proposal.status} "
            f"(상계 {offset_id})"
        )
    before = proposal.status
    proposal.agency_consent = consent
    proposal.consent_provenance = Provenance.MOCK
    proposal.consented_at = func.now()
    if consent == AgencyConsent.REFUSE:
        proposal.status = OffsetStatus.CONSENT_REFUSED
        _log(
            session,
            proposal,
            before,
            actor=AGENCY_ACTOR,
            role=AGENCY_ROLE,
            reason="대리점 상계 거절 [모의] — 전액 지급 대상",
        )
        return proposal, claim

    _settle(session, proposal, claim)
    proposal.status = OffsetStatus.SETTLED
    amount = proposal.offset_amount_krw
    _log(
        session,
        proposal,
        before,
        actor=AGENCY_ACTOR,
        role=AGENCY_ROLE,
        reason=f"대리점 상계 동의 [모의] — 채권 {amount:,}원 상계",
    )
    if payable_krw(session, claim) == 0:
        transition(
            session,
            claim,
            ClaimStatus.OFFSET_DONE,
            actor=AGENCY_ACTOR,
            actor_role=AGENCY_ROLE,
            reason=f"대리점 상계 동의 [모의] — 장려금 {amount:,}원 전액 상계",
            payload={"offset_id": offset_id},
        )
    return proposal, claim


def _settle(session: Session, proposal: OffsetProposal, claim: RebateClaim) -> None:
    """상계액을 연체 채권에 순서대로 나눠 잔액 조정을 남긴다. 원본 잔액은 바꾸지 않는다."""
    items = overdue_items(session, proposal.group_id, claim.agency_id)
    left = proposal.offset_amount_krw
    available = sum(i.remaining_krw for i in items)
    # 결정 뒤 다른 건이 먼저 상계해 잔액이 모자랄 수 있다. 일부만 상계하지 않고 막는다.
    if available < left:
        raise InvalidTransitionError(
            f"그룹 연체 잔액 {available:,}원이 상계액 {left:,}원보다 적습니다 "
            f"(상계 {proposal.offset_id})"
        )
    for item in items:
        take = min(left, item.remaining_krw)
        if take <= 0:
            continue
        session.add(
            ARAdjustment(
                ar_id=item.ar_id,
                offset_id=proposal.offset_id,
                amount_krw=take,
                provenance=Provenance.ASSUMED,
            )
        )
        left -= take
        if left == 0:
            break
    session.flush()


def cancel_open_offsets(session: Session, rebate_ids: list[str]) -> None:
    """정정 신고로 재검토필요가 된 건의 열린 제안을 취소한다(20). 확정된 상계는 그대로 둔다."""
    session.execute(
        update(OffsetProposal)
        .where(
            OffsetProposal.rebate_id.in_(rebate_ids),
            OffsetProposal.status.in_(OPEN_OFFSET),
        )
        .values(status=OffsetStatus.CANCELLED)
    )


def offset_out(session: Session, proposal: OffsetProposal) -> OffsetOut:
    claim = session.get(RebateClaim, proposal.rebate_id)
    adjustments = session.scalars(
        select(ARAdjustment)
        .where(ARAdjustment.offset_id == proposal.offset_id)
        .order_by(ARAdjustment.id)
    ).all()
    return OffsetOut(
        offset_id=proposal.offset_id,
        rebate_id=proposal.rebate_id,
        group_label=session.get(RelatedGroup, proposal.group_id).label,
        overdue_total_krw=proposal.overdue_total_krw,
        max_offset_krw=proposal.max_offset_krw,
        status=proposal.status,
        ai_amount_krw=proposal.ai_amount_krw,
        ai_rationale=proposal.ai_rationale,
        ai_counter_evidence=proposal.ai_counter_evidence,
        ai_confidence=proposal.ai_confidence,
        verified=proposal.verified,
        fallback_used=proposal.fallback_used,
        model=proposal.model,
        finance_decision=proposal.finance_decision,
        offset_amount_krw=proposal.offset_amount_krw,
        finance_reason=proposal.finance_reason,
        decided_by=proposal.decided_by,
        decided_at=proposal.decided_at,
        agreed=proposal.agreed,
        agency_consent=proposal.agency_consent,
        consent_provenance=proposal.consent_provenance,
        consented_at=proposal.consented_at,
        created_at=proposal.created_at,
        overdue_items=overdue_items(session, proposal.group_id, claim.agency_id),
        adjustments=[ARAdjustmentOut.model_validate(a) for a in adjustments],
    )


def list_offsets(session: Session, rebate_id: str) -> list[OffsetOut]:
    proposals = session.scalars(
        select(OffsetProposal)
        .where(OffsetProposal.rebate_id == rebate_id)
        .order_by(OffsetProposal.offset_id)
    ).all()
    return [offset_out(session, p) for p in proposals]
