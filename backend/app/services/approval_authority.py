"""결재 권한 판정(가드의 기준).

대상월(period_ym)마다 판정 단위로 장려금을 합산해 규정상 최소 결재권자를 계산한다.
판정 단위는 지금 버전의 관련자 그룹이고, 그룹이 없는 대리점은 혼자다.
반려 건은 지급되지 않으므로 합산에서 뺀다. 200만원 이하는 영업지원팀 전결, 초과는 영업임원.
AI 가드(17)가 이 값을 하한으로 쓴다. AI 는 결재 단계를 올릴 수만 있다.

계산(decide_authority)은 DB 를 모르는 순수 함수이고, 저장은 assess_period 가 한다.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GroupMember, GroupVersion, RebateClaim, RelatedGroup
from app.models.enums import ApproverRole, ClaimStatus

# "거래처별 월 지급액 2백만원 이하는 영업지원팀 전결" — approval_authority_policy.md
REBATE_LIMIT_KRW = 2_000_000


@dataclass(frozen=True)
class AuthorityDecision:
    rebate_id: str
    # 판정 당시 그룹. 단독 대리점이면 None.
    group_id: int | None
    group_sum_krw: int
    min_authority: ApproverRole


def required_authority(group_sum_krw: int) -> ApproverRole:
    """판정 단위 월 합산으로 최소 결재권자를 정한다. 한도 '이하'는 전결이다."""
    if group_sum_krw <= REBATE_LIMIT_KRW:
        return ApproverRole.SALES_SUPPORT
    return ApproverRole.SALES_EXECUTIVE


def has_authority(role: str, required: str) -> bool:
    """role 이 required 이상의 결재권자인지 답한다. 결재권자가 아닌 역할은 늘 거짓이다.

    DB 나 요청 본문에서 온 문자열을 그대로 넣어도 된다(StrEnum 은 같은 글자와 같다).
    AI 가드(17)도 이 함수로 "AI 판단이 최소 결재권자보다 낮은가"를 본다.
    """
    order = list(ApproverRole)
    if role not in order or required not in order:
        return False
    return order.index(role) >= order.index(required)


def decide_authority(
    claims: Iterable[RebateClaim], group_of: Mapping[str, int]
) -> list[AuthorityDecision]:
    """장려금 건마다 판정 단위 합산과 최소 결재권자를 계산한다.

    group_of 는 대리점 → 지금 버전 그룹 ID. 그룹이 없는 대리점은 키가 없다.
    """
    # 반복자는 한 번 돌면 비므로, 합산과 판정에서 두 번 쓰려고 목록으로 받는다.
    payable = [c for c in claims if c.status != ClaimStatus.REJECTED]

    def unit(claim: RebateClaim) -> tuple[str, int | str]:
        # 달이 섞여 들어와도 달마다 따로 합산한다. 그룹이 없으면 대리점 ID 가 단위다.
        return claim.period_ym, group_of.get(claim.agency_id, claim.agency_id)

    sums: defaultdict[tuple[str, int | str], int] = defaultdict(int)
    for claim in payable:
        sums[unit(claim)] += claim.rebate_amount_krw

    decisions = [
        AuthorityDecision(
            rebate_id=claim.rebate_id,
            group_id=group_of.get(claim.agency_id),
            group_sum_krw=sums[unit(claim)],
            min_authority=required_authority(sums[unit(claim)]),
        )
        for claim in payable
    ]
    return sorted(decisions, key=lambda d: d.rebate_id)


def current_group_of(session: Session) -> dict[str, int]:
    """지금 버전 그룹의 대리점 → 그룹 ID. 옛 버전 그룹은 남아 있어도 빼고 본다."""
    rows = session.execute(
        select(GroupMember.agency_id, GroupMember.group_id)
        .join(RelatedGroup, RelatedGroup.group_id == GroupMember.group_id)
        .join(
            GroupVersion,
            GroupVersion.group_version_id == RelatedGroup.group_version_id,
        )
        .where(GroupVersion.is_current)
    )
    return dict(rows.all())


def assess_period(session: Session, period_ym: str) -> list[AuthorityDecision]:
    """대상월 하나를 판정해 장려금 건에 최소 결재권자 · 그룹 · 합산액을 채운다.

    업무 상태(status)는 바꾸지 않고, commit 하지 않는다.
    08 접수에서 상태 변경과 한 트랜잭션으로 묶인다.
    """
    claims = session.scalars(
        select(RebateClaim).where(RebateClaim.period_ym == period_ym)
    ).all()
    decisions = decide_authority(claims, current_group_of(session))
    by_id = {d.rebate_id: d for d in decisions}

    for claim in claims:
        decision = by_id.get(claim.rebate_id)
        if decision is None:
            # 반려 건. 다시 판정할 때 이전 판정 값이 남지 않게 비운다.
            claim.min_authority = claim.group_id = claim.group_sum_krw = None
            continue
        claim.min_authority = decision.min_authority
        claim.group_id = decision.group_id
        claim.group_sum_krw = decision.group_sum_krw

    session.flush()
    return decisions
