"""감사 사후 검토(24): 이미 지급된 과거 건을 지금 그룹으로 다시 판정해, 결재 단계가 모자랐던 건에 감사 작업을 연다.

대상은 원본에서 승인 · 지급된 건(original_status 승인, 지금 상태 지급완료)이다. 앱에서 결재 경로를 거친 6월분은 빠진다.
계산은 한도 판정 코드(06 decide_authority)를 그대로 쓴다. 건의 판정 컬럼(min_authority 등)에는 쓰지 않는다
— 1~5월 건에 지금 그룹을 적으면 "판정 당시 그룹"이라는 뜻이 깨지기 때문이다(06 결정).
위반 = 규정상 최소 결재권자가 영업임원인데 원본 결재자가 그보다 낮은 건. 원본 기준 G1 15건 22,238,349원.
같은 건에 열린 · 닫힌 사후 검토 작업이 이미 있으면 다시 만들지 않는다(여러 번 눌러도 안전). commit 하지 않는다.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RebateClaim, RelatedGroup, Task
from app.models.enums import ClaimStatus, Department
from app.schemas.audit import RetroFinding, RetroReviewResult
from app.services.approval import InsufficientAuthorityError
from app.services.approval_authority import (
    REBATE_LIMIT_KRW,
    current_group_of,
    decide_authority,
    has_authority,
)
from app.services.task_dispatcher import create_task

logger = logging.getLogger(__name__)

RETRO_TASK = "사후 검토"
# 원본 approval_status 값. 원본에서 이미 지급된 건만 사후 검토 대상이다.
ORIGINAL_APPROVED = "승인"


def run_retro_review(session: Session, *, actor: str, role: str) -> RetroReviewResult:
    """원본 지급 건을 다시 판정해 위반 건마다 내부감사 사후 검토 작업을 연다. 내부감사만."""
    if role != Department.AUDIT:
        raise InsufficientAuthorityError(
            f"{role} 은(는) 사후 검토를 실행할 수 없습니다. 내부감사만 실행합니다"
        )
    paid = session.scalars(
        select(RebateClaim).where(
            RebateClaim.original_status == ORIGINAL_APPROVED,
            RebateClaim.status == ClaimStatus.PAID,
        )
    ).all()
    periods = sorted({c.period_ym for c in paid})
    # 합산은 그 달의 모든 건으로 한다(반려는 decide_authority 가 뺀다). 지급 건만 더하면 같은 결과지만,
    # 한도 판정(06)과 같은 입력을 써야 "같은 규칙으로 다시 계산했다"고 말할 수 있다.
    month_claims = session.scalars(
        select(RebateClaim).where(RebateClaim.period_ym.in_(periods))
    ).all()
    decisions = {
        d.rebate_id: d
        for d in decide_authority(month_claims, current_group_of(session))
    }
    already = set(
        session.scalars(
            select(Task.ref_id).where(
                Task.dept == Department.AUDIT, Task.task_type == RETRO_TASK
            )
        )
    )

    findings = []
    for claim in sorted(paid, key=lambda c: c.rebate_id):
        decision = decisions[claim.rebate_id]
        approver = claim.original_approver or "없음"
        if has_authority(approver, decision.min_authority):
            continue
        label = (
            session.get(RelatedGroup, decision.group_id).label
            if decision.group_id is not None
            else None
        )
        task_id = None
        if claim.rebate_id not in already:
            task_id = create_task(
                session,
                dept=Department.AUDIT,
                task_type=RETRO_TASK,
                ref_id=claim.rebate_id,
                detail=(
                    f"{claim.period_ym} {label or claim.agency_id} 합산 "
                    f"{decision.group_sum_krw:,}원 > 한도 {REBATE_LIMIT_KRW:,}원 → "
                    f"최소 결재권자 {decision.min_authority}, 실제 {approver} 전결로 "
                    f"{claim.rebate_amount_krw:,}원 지급({claim.original_payment_date}) [원본]"
                ),
            ).task_id
        findings.append(
            RetroFinding(
                rebate_id=claim.rebate_id,
                agency_id=claim.agency_id,
                period_ym=claim.period_ym,
                group_label=label,
                group_sum_krw=decision.group_sum_krw,
                min_authority=decision.min_authority,
                original_approver=approver,
                rebate_amount_krw=claim.rebate_amount_krw,
                original_payment_date=claim.original_payment_date,
                task_id=task_id,
            )
        )
    created = sum(1 for f in findings if f.task_id is not None)
    logger.info(
        "사후 검토(%s): 지급 건 %d건 중 위반 %d건(%s원), 새 감사 작업 %d건",
        actor,
        len(paid),
        len(findings),
        f"{sum(f.rebate_amount_krw for f in findings):,}",
        created,
    )
    return RetroReviewResult(
        checked=len(paid),
        periods=periods,
        findings=findings,
        total_krw=sum(f.rebate_amount_krw for f in findings),
        created_tasks=created,
    )
