"""상신 결재: 승인 요청 만들기, 상신 건 결정, 전결 건 결정.

결정하는 역할이 요구 역할 이상인지(has_authority)를 상태 머신(claim_state) 앞에서 검사한다.
상태 머신은 기록만 하고 권한은 보지 않기 때문이다. commit 은 요청 의존성이 한다.
결정자 이름 · 역할은 시연용으로 요청 본문에서 받는다(실제 시스템이면 로그인 토큰에서).
"""

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ApprovalItem, ApprovalRequest, RebateClaim
from app.models.enums import ClaimStatus, Decision
from app.services.approval_authority import has_authority
from app.services.claim_state import InvalidTransitionError, transition

# 결정 → 건의 다음 상태. 승인 뒤 단계(상계검토 · 지급지시)는 11 · 22 에서 이어진다.
DECISION_TO_STATUS = {
    Decision.APPROVE: ClaimStatus.APPROVED,
    Decision.REJECT: ClaimStatus.REJECTED,
}


# 정정 신고로 판정 단위가 바뀌어 더는 결정할 수 없는 승인 요청의 decision 값(20).
CANCELLED_REQUEST = "취소"


class InsufficientAuthorityError(Exception):
    """결정하는 역할이 요구 역할보다 낮다(API 403)."""


def open_approval_requests(
    session: Session, claims: Iterable[RebateClaim]
) -> list[ApprovalRequest]:
    """상신대기로 간 건을 판정 단위마다 묶어 승인 요청과 포함 건을 만든다."""
    units: dict[int | str, list[RebateClaim]] = {}
    for claim in claims:
        # 06 과 같은 판정 단위: 그룹이 있으면 그룹, 없으면 대리점 혼자.
        key = claim.group_id if claim.group_id is not None else claim.agency_id
        units.setdefault(key, []).append(claim)

    requests = []
    for members in units.values():
        # 같은 판정 단위의 건은 06 이 같은 합산액을 채웠다. 다시 더하지 않고 옮긴다.
        first = members[0]
        request = ApprovalRequest(
            group_id=first.group_id,
            period_ym=first.period_ym,
            group_sum_krw=first.group_sum_krw,
            approver_role=first.min_authority,
        )
        session.add(request)
        # 포함 건이 가리킬 request_id 를 받으려면 먼저 DB 에 넣어야 한다.
        session.flush()
        session.add_all(
            ApprovalItem(request_id=request.request_id, rebate_id=c.rebate_id)
            for c in members
        )
        requests.append(request)
    session.flush()
    return requests


def decide_approval(
    session: Session,
    request_id: int,
    *,
    decision: Decision,
    reason: str,
    actor: str,
    role: str,
) -> tuple[ApprovalRequest, list[RebateClaim]]:
    """승인 요청을 결정하고, 포함 건을 모두 승인 또는 반려로 바꾼다."""
    request = session.get(ApprovalRequest, request_id)
    if request is None:
        raise LookupError(f"승인 요청 {request_id} 이(가) 없습니다")
    # 취소된 요청은 포함 건이 떨어져 나가 있어 상태 머신이 막지 못한다(건이 없으니 전이도 없다).
    # 승인 · 반려로 이미 결정된 요청은 지금처럼 상태 머신이 막는다.
    if request.decision == CANCELLED_REQUEST:
        raise InvalidTransitionError(
            f"정정 신고로 취소된 승인 요청입니다: {request.reason} (요청 {request_id})"
        )
    # 권한이 없으면 아무것도 바꾸지 않고 끝나야 하므로 전이보다 앞에서 본다.
    if not has_authority(role, request.approver_role):
        raise InsufficientAuthorityError(
            f"{role} 은(는) {request.approver_role} 결재 건을 결정할 수 없습니다 "
            f"(요청 {request_id})"
        )

    claims = session.scalars(
        select(RebateClaim)
        .join(ApprovalItem, ApprovalItem.rebate_id == RebateClaim.rebate_id)
        .where(ApprovalItem.request_id == request_id)
        .order_by(RebateClaim.rebate_id)
    ).all()
    why = reason.strip() or f"{role} {decision}"
    # 이미 결정된 요청이면 여기서 상태 머신이 막는다(409). 요청 기록보다 먼저 둔다.
    for claim in claims:
        transition(
            session,
            claim,
            DECISION_TO_STATUS[decision],
            actor=actor,
            actor_role=role,
            reason=why,
            payload={"request_id": request_id},
        )

    request.decision = decision
    request.reason = reason.strip() or None
    request.decided_by = actor
    # SQL 함수를 넣으면 flush 때 DB 가 시각을 채운다(UTC).
    request.decided_at = func.now()
    session.flush()
    return request, claims


def decide_claim(
    session: Session,
    rebate_id: str,
    *,
    decision: Decision,
    reason: str,
    actor: str,
    role: str,
) -> RebateClaim:
    """전결대기 건 하나를 승인 또는 반려한다."""
    claim = session.get(RebateClaim, rebate_id)
    if claim is None:
        raise LookupError(f"장려금 건 {rebate_id} 이(가) 없습니다")
    # 전이표에는 상신대기 → 승인이 있다. 이 길을 열면 승인 요청 기록 없이 상신 건이 승인된다.
    if claim.status != ClaimStatus.AWAITING_SUPPORT:
        raise InvalidTransitionError(
            f"전결 결정은 전결대기 건만 할 수 있습니다: {claim.status} ({rebate_id})"
        )
    if not has_authority(role, claim.min_authority):
        raise InsufficientAuthorityError(
            f"{role} 은(는) {claim.min_authority} 결재 건을 결정할 수 없습니다 "
            f"({rebate_id})"
        )

    transition(
        session,
        claim,
        DECISION_TO_STATUS[decision],
        actor=actor,
        actor_role=role,
        reason=reason.strip() or f"{role} {decision}",
    )
    return claim
