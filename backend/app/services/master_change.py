"""마스터 정정 적용: 식별정보 유효기간을 갱신하고, 그룹을 새 버전으로 다시 계산해 영향받는 건을 다시 판정한다.

흐름(모두 한 트랜잭션, commit 하지 않는다):
1. 이전 값의 valid_to 를 정정일로 닫고 새 값 행을 더한다. 원본 대리점 마스터와 이전 행은 지우지 않는다.
2. 모든 식별속성으로 관련자를 다시 계산해 새 GroupVersion 으로 저장한다(정정 전 버전은 그대로 남는다).
3. 소속 그룹이 달라진 대리점의 아직 돈이 나가지 않은 건을 재검토필요로 돌린다.
   그룹이 그대로면 영향받는 건이 없다 — 정정했는데도 결론이 유지되는 경우다(근거는 결과의 evidence).
4. 그중 결재 대기(전결대기 · 상신대기)였던 건은 코드가 바로 다시 판정해 결재 경로에 올린다.
   AI 가 아니라 한도 판정 코드(06)의 계산이라 사람 결정을 대신하지 않는다. 그 밖의 상태(승인 · 소명대기 ·
   지급보류 등)는 재검토필요로 두고, 영업지원팀이 rejudge_claim 으로 직접 다시 판정한다.
   AI 검토(claim_review)는 다시 판정된 건 상세에서 사람이 누른다.
열려 있던 승인 요청은 판정 단위가 바뀌어 결정할 수 없으므로 취소하고, 열린 소명 요청 · 상계 제안도 취소한다.
"""

import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import date

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.models import (
    Agency,
    ApprovalItem,
    ApprovalRequest,
    EventLog,
    ExplanationRequest,
    GroupMember,
    GroupVersion,
    IdentityAttribute,
    MasterChange,
    RebateClaim,
    RelatedGroup,
    RelationEdge,
)
from app.models.enums import (
    ApproverRole,
    ClaimStatus,
    ExplanationStatus,
    Provenance,
)
from app.schemas.master_change import (
    CORRECTABLE,
    ClaimImpactOut,
    GroupOut,
    MasterChangeOut,
    MasterChangeResult,
)
from app.schemas.related_party import RelationEdgeOut
from app.services.approval import (
    CANCELLED_REQUEST,
    InsufficientAuthorityError,
)
from app.services.claim_state import REVIEW_FROM, InvalidTransitionError, transition
from app.services.explanation import OPEN_STATUSES
from app.services.intake import SYSTEM_ACTOR
from app.services.offset import cancel_open_offsets
from app.services.rejudge import latest_request_id, rejudge_claims
from app.services.related_party import find_related_parties, save_group_version

logger = logging.getLogger(__name__)

# 코드가 바로 다시 판정하는 상태: 결재 단계만 다시 정해지면 되는 건.
AUTO_REJUDGE = frozenset({ClaimStatus.AWAITING_SUPPORT, ClaimStatus.AWAITING_EXECUTIVE})


class InvalidMasterChangeError(ValueError):
    """정정할 수 없는 신고(같은 값 · 빈 값 · 정정일 오류 등). API 는 422 로 돌려준다."""


def _groups(session: Session, version_id: int) -> list[GroupOut]:
    """버전 하나의 그룹들(그룹 ID 순). 그룹 안은 대리점 ID 순."""
    members: defaultdict[int, list[str]] = defaultdict(list)
    for group_id, agency_id in session.execute(
        select(GroupMember.group_id, GroupMember.agency_id)
        .join(RelatedGroup, RelatedGroup.group_id == GroupMember.group_id)
        .where(RelatedGroup.group_version_id == version_id)
        .order_by(GroupMember.group_id, GroupMember.agency_id)
    ):
        members[group_id].append(agency_id)
    labels = session.execute(
        select(RelatedGroup.group_id, RelatedGroup.label)
        .where(RelatedGroup.group_version_id == version_id)
        .order_by(RelatedGroup.group_id)
    ).all()
    return [GroupOut(label=label, members=members[gid]) for gid, label in labels]


def _member_map(groups: Iterable[GroupOut]) -> dict[str, tuple[str, ...]]:
    return {m: tuple(g.members) for g in groups for m in g.members}


def apply_master_change(
    session: Session,
    agency_id: str,
    *,
    attr_type: str,
    new_value: str,
    effective_date: date | None,
    reported_text: str,
    actor: str,
    role: str,
) -> MasterChangeResult:
    """정정 신고를 적용하고 그룹 변화와 영향받은 건을 돌려준다. 영업지원팀만."""
    if session.get(Agency, agency_id) is None:
        raise LookupError(f"대리점 {agency_id} 이(가) 없습니다")
    if role != ApproverRole.SALES_SUPPORT:
        raise InsufficientAuthorityError(
            f"{role} 은(는) 마스터 정정 신고를 적용할 수 없습니다 ({agency_id})"
        )
    if attr_type not in CORRECTABLE:
        raise InvalidMasterChangeError("대표자 · 주소 · 등록계좌만 정정할 수 있습니다")
    new_value = new_value.strip()
    if not new_value:
        raise InvalidMasterChangeError("새 값을 입력해야 합니다")
    effective = effective_date or date.today()

    current = session.scalar(
        select(IdentityAttribute)
        .where(
            IdentityAttribute.agency_id == agency_id,
            IdentityAttribute.attr_type == attr_type,
            IdentityAttribute.valid_to.is_(None),
        )
        .order_by(IdentityAttribute.id.desc())
        .limit(1)
    )
    if current is None:
        raise InvalidMasterChangeError(f"{agency_id} 의 현재 {attr_type} 값이 없습니다")
    if current.value == new_value:
        raise InvalidMasterChangeError(f"이미 같은 {attr_type} 값입니다: {new_value}")
    if effective < current.valid_from:
        raise InvalidMasterChangeError(
            f"정정일 {effective} 이(가) 현재 값의 시작일 {current.valid_from} 보다 이릅니다"
        )

    before_version = session.scalar(select(GroupVersion).where(GroupVersion.is_current))
    groups_before = _groups(session, before_version.group_version_id)
    change = MasterChange(
        agency_id=agency_id,
        attr_type=attr_type,
        old_value=current.value,
        new_value=new_value,
        effective_date=effective,
        reported_text=reported_text.strip() or None,
        reported_by=actor,
        provenance=Provenance.CLAIMED,
        group_version_before=before_version.group_version_id,
    )
    session.add(change)
    # 새 값 행의 출처("master_change:번호")에 쓸 번호를 먼저 받는다.
    session.flush()

    current.valid_to = effective
    session.add(
        IdentityAttribute(
            agency_id=agency_id,
            attr_type=attr_type,
            value=new_value,
            provenance=Provenance.CLAIMED,
            source_ref=f"master_change:{change.change_id}",
            valid_from=effective,
        )
    )
    session.flush()

    after_version = save_group_version(
        session, find_related_parties(session.scalars(select(IdentityAttribute)).all())
    )
    change.group_version_after = after_version.group_version_id
    groups_after = _groups(session, after_version.group_version_id)

    before_map, after_map = _member_map(groups_before), _member_map(groups_after)
    affected = sorted(
        a
        for a in before_map.keys() | after_map.keys()
        if before_map.get(a) != after_map.get(a)
    )

    impacts = _reopen_claims(session, affected, change=change, actor=actor, role=role)
    session.add(
        EventLog(
            actor=actor,
            actor_role=role,
            entity_type="master_change",
            entity_id=str(change.change_id),
            from_status=change.old_value,
            to_status=new_value,
            reason=f"{agency_id} {attr_type} 정정 신고 적용",
            payload={
                "version_before": before_version.version_no,
                "version_after": after_version.version_no,
                "group_retained": not affected,
                "affected_agencies": affected,
            },
        )
    )
    session.flush()

    edges = session.scalars(
        select(RelationEdge)
        .where(
            RelationEdge.group_version_id == after_version.group_version_id,
            or_(RelationEdge.agency_a == agency_id, RelationEdge.agency_b == agency_id),
        )
        .order_by(RelationEdge.edge_id)
    ).all()
    logger.info(
        "정정 신고 #%d 적용: %s %s, 그룹 %s, 영향 건 %d",
        change.change_id,
        agency_id,
        attr_type,
        "유지" if not affected else "변경",
        len(impacts),
    )
    return MasterChangeResult(
        change=MasterChangeOut.model_validate(change),
        version_no_before=before_version.version_no,
        version_no_after=after_version.version_no,
        groups_before=groups_before,
        groups_after=groups_after,
        group_retained=not affected,
        affected_agencies=affected,
        evidence=[RelationEdgeOut.model_validate(e) for e in edges],
        claims=impacts,
    )


def _reopen_claims(
    session: Session,
    affected: list[str],
    *,
    change: MasterChange,
    actor: str,
    role: str,
) -> list[ClaimImpactOut]:
    """소속 그룹이 달라진 대리점의 돈이 안 나간 건을 재검토필요로 돌리고, 결재 대기였던 건은 다시 판정한다."""
    if not affected:
        return []
    claims = session.scalars(
        select(RebateClaim)
        .where(
            RebateClaim.agency_id.in_(affected),
            RebateClaim.status.in_(list(REVIEW_FROM)),
        )
        .order_by(RebateClaim.rebate_id)
    ).all()
    if not claims:
        return []

    ids = [c.rebate_id for c in claims]
    before = {c.rebate_id: (c.status, c.min_authority, c.group_sum_krw) for c in claims}
    _cancel_open_requests(session, ids, change)
    session.execute(
        update(ExplanationRequest)
        .where(
            ExplanationRequest.rebate_id.in_(ids),
            ExplanationRequest.status.in_(OPEN_STATUSES),
        )
        .values(status=ExplanationStatus.CANCELLED)
    )
    # 상계 한도는 판정 당시 그룹의 연체 채권으로 계산했다. 그룹이 바뀌면 다시 승인될 때 새로 만든다.
    cancel_open_offsets(session, ids)
    for claim in claims:
        transition(
            session,
            claim,
            ClaimStatus.NEEDS_REVIEW,
            actor=actor,
            actor_role=role,
            reason=(
                f"정정 신고 #{change.change_id}: {change.agency_id} "
                f"{change.attr_type} 변경으로 판정 단위가 바뀜"
            ),
            payload={"change_id": change.change_id},
        )
    rejudge_claims(
        session,
        [c for c in claims if before[c.rebate_id][0] in AUTO_REJUDGE],
        actor=actor,
        role=role,
        reason=f"정정 신고 #{change.change_id} 반영 재판정",
    )

    impacts = []
    for claim in claims:
        from_status, min_before, sum_before = before[claim.rebate_id]
        judged = claim.status in AUTO_REJUDGE
        impacts.append(
            ClaimImpactOut(
                rebate_id=claim.rebate_id,
                agency_id=claim.agency_id,
                period_ym=claim.period_ym,
                from_status=from_status,
                to_status=claim.status,
                min_authority_before=min_before,
                min_authority_after=claim.min_authority if judged else None,
                group_sum_before=sum_before,
                group_sum_after=claim.group_sum_krw if judged else None,
                approval_request_id=(
                    latest_request_id(session, claim.rebate_id)
                    if claim.status == ClaimStatus.AWAITING_EXECUTIVE
                    else None
                ),
            )
        )
    return impacts


def _cancel_open_requests(
    session: Session, rebate_ids: list[str], change: MasterChange
) -> None:
    """정정으로 판정 단위가 바뀐 건이 든 열린 승인 요청을 취소한다. 포함 건은 사유 문장에 남기고 떼어 낸다."""
    requests = session.scalars(
        select(ApprovalRequest)
        .join(ApprovalItem, ApprovalItem.request_id == ApprovalRequest.request_id)
        .where(
            ApprovalItem.rebate_id.in_(rebate_ids), ApprovalRequest.decision.is_(None)
        )
        .distinct()
    ).all()
    for request in requests:
        members = session.scalars(
            select(ApprovalItem.rebate_id)
            .where(ApprovalItem.request_id == request.request_id)
            .order_by(ApprovalItem.rebate_id)
        ).all()
        request.decision = CANCELLED_REQUEST
        request.reason = (
            f"정정 신고 #{change.change_id} 로 판정 단위가 바뀌어 취소 "
            f"(포함 건: {', '.join(members)})"
        )
        request.decided_by = SYSTEM_ACTOR
        request.decided_at = func.now()
        # 떼어 내야 건 상세의 승인 요청 칸과 AI 검토 단위가 취소된 요청을 가리키지 않는다.
        session.execute(
            delete(ApprovalItem).where(ApprovalItem.request_id == request.request_id)
        )
    session.flush()


def rejudge_claim(
    session: Session, rebate_id: str, *, actor: str, role: str
) -> RebateClaim:
    """재검토필요 건 하나를 영업지원팀이 직접 다시 판정한다(자동 재판정 대상이 아니었던 건)."""
    claim = session.get(RebateClaim, rebate_id)
    if claim is None:
        raise LookupError(f"장려금 건 {rebate_id} 이(가) 없습니다")
    if role != ApproverRole.SALES_SUPPORT:
        raise InsufficientAuthorityError(
            f"{role} 은(는) 재판정할 수 없습니다 ({rebate_id})"
        )
    if claim.status != ClaimStatus.NEEDS_REVIEW:
        raise InvalidTransitionError(
            f"재판정은 재검토필요 건만 할 수 있습니다: {claim.status} ({rebate_id})"
        )
    rejudge_claims(
        session, [claim], actor=actor, role=role, reason="재검토필요 건 재판정"
    )
    return claim
