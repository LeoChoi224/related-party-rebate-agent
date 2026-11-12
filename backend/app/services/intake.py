"""장려금 접수.

지정한 대상월의 장려금 건을 모두 미접수 → 접수 → (한도 판정) → 관계확인 → 전결대기 /
상신대기로 보낸다. 전부 한 트랜잭션이고 commit 은 요청 의존성(api/deps.py)이 한다.
이미 처리한 달을 다시 접수하면 상태 머신이 막는다(InvalidTransitionError → 409).
상신대기로 간 건은 판정 단위마다 승인 요청을 함께 만든다(09).
정황 관계 대리점의 건은 영업지원팀 소명 요청 작업을 만든다(R3, 지급은 막지 않는다).
AI 검토(claim_review 그래프)는 17 에서 붙인다.
"""

import logging
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RebateClaim
from app.models.enums import ApproverRole, ClaimStatus
from app.services.approval import open_approval_requests
from app.services.approval_authority import assess_period
from app.services.claim_state import transition
from app.services.task_dispatcher import open_circumstantial_tasks

logger = logging.getLogger(__name__)

# 최소 결재권자 → 다음 상태. 결재 단계가 늘면 한 줄을 더한다.
NEXT_STATUS = {
    ApproverRole.SALES_SUPPORT: ClaimStatus.AWAITING_SUPPORT,
    ApproverRole.SALES_EXECUTIVE: ClaimStatus.AWAITING_EXECUTIVE,
}
# 역할 선택(12) 전까지는 시스템이 접수한다.
SYSTEM_ACTOR = "시스템"


def intake_period(session: Session, period_ym: str) -> dict[str, int]:
    """대상월을 접수해 결재 경로에 올리고, 상태별 건수를 돌려준다."""
    # 이력 순서와 막힌 건 ID 가 매번 같게 rebate_id 순으로 처리한다.
    claims = session.scalars(
        select(RebateClaim)
        .where(RebateClaim.period_ym == period_ym)
        .order_by(RebateClaim.rebate_id)
    ).all()
    if not claims:
        raise LookupError(f"{period_ym} 장려금 건이 없습니다")
    who = {"actor": SYSTEM_ACTOR, "actor_role": SYSTEM_ACTOR}

    # 판정은 한 달 전체를 합산하므로, 모든 건이 접수될 수 있는지 먼저 끝낸다.
    for claim in claims:
        transition(
            session, claim, ClaimStatus.RECEIVED, reason=f"{period_ym}분 접수", **who
        )

    decisions = {d.rebate_id: d for d in assess_period(session, period_ym)}
    for claim in claims:
        decision = decisions[claim.rebate_id]
        transition(
            session,
            claim,
            ClaimStatus.RELATION_CHECKED,
            reason="관련자 그룹 · 한도 판정",
            payload={
                "group_id": decision.group_id,
                "group_sum_krw": decision.group_sum_krw,
                "min_authority": decision.min_authority,
            },
            **who,
        )
        transition(
            session,
            claim,
            NEXT_STATUS[decision.min_authority],
            reason=(
                f"판정 단위 합산 {decision.group_sum_krw:,}원 → "
                f"최소 결재권자 {decision.min_authority}"
            ),
            **who,
        )

    # 세션 안의 status 는 방금 넣은 enum 이라, 로그 · 응답이 한글만 보이게 str 로 바꾼다.
    # 같은 트랜잭션에서 만들어, 상신대기인데 승인 요청이 없는 건이 생기지 않게 한다.
    open_approval_requests(
        session, [c for c in claims if c.status == ClaimStatus.AWAITING_EXECUTIVE]
    )

    # R3: 정황은 지급을 막지 않고 소명 요청 작업만 연다.
    open_circumstantial_tasks(session, claims)

    by_status = dict(Counter(str(claim.status) for claim in claims))
    logger.info("%s 장려금 %d건을 접수했습니다: %s", period_ym, len(claims), by_status)
    return by_status
