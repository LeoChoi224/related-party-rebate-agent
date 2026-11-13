"""정정 신고 문장 처리(19): 신고 문장 기록 → AI 해석(그래프) → 영업지원팀 확인(적용 · 기각).

적용은 사람이 확인하거나 고친 값으로 20 의 apply_master_change 를 그대로 부른다. AI 해석은 폼을 채우는 앞단일 뿐이다.
AI 해석과 다른 값으로 적용하면 사유가 있어야 한다(25 와 같은 규칙). 대체 모드면 비교할 해석이 없다.
commit 하지 않는다. 그래프 재개는 확인 API 가 이 서비스가 끝난 뒤에 한다(17).
"""

from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import MasterChangeReport
from app.models.enums import ApproverRole, Provenance, ReportStatus
from app.schemas.master_change import MasterChangeResult
from app.services.ai_agreement import require_reason
from app.services.approval import InsufficientAuthorityError
from app.services.claim_state import InvalidTransitionError
from app.services.master_change import apply_master_change


def _support_only(role: str, what: str) -> None:
    if role != ApproverRole.SALES_SUPPORT:
        raise InsufficientAuthorityError(
            f"{role} 은(는) {what} 수 없습니다. 영업지원팀만 합니다"
        )


def create_report(
    session: Session, raw_text: str, *, actor: str, role: str
) -> MasterChangeReport:
    """신고 문장을 [주장] 으로 기록한다. 해석은 라우트가 그래프로 이어서 돌린다."""
    _support_only(role, "정정 신고를 받을")
    report = MasterChangeReport(
        raw_text=raw_text.strip(),
        provenance=Provenance.CLAIMED,
        reported_by=actor,
        status=ReportStatus.AWAITING,
        problems=[],
    )
    session.add(report)
    session.flush()
    return report


def _describe(
    agency_id: str | None, attr_type: str | None, value: str | None, when
) -> str:
    when_text = f", {when}" if when else ""
    return f"{agency_id} {attr_type} → {value}{when_text}"


def decide_report(
    session: Session,
    report_id: int,
    *,
    apply: bool,
    agency_id: str,
    attr_type: str | None,
    new_value: str,
    effective_date: date | None,
    reason: str,
    actor: str,
    role: str,
) -> tuple[MasterChangeReport, MasterChangeResult | None]:
    """영업지원팀이 해석을 확인한다. 적용이면 정정을 적용하고 신고가 그 정정을 가리킨다."""
    report = session.get(MasterChangeReport, report_id)
    if report is None:
        raise LookupError(f"정정 신고 문장 {report_id} 이(가) 없습니다")
    _support_only(role, "정정 신고를 확인할")
    if report.status != ReportStatus.AWAITING:
        raise InvalidTransitionError(
            f"이미 확인한 정정 신고입니다: {report.status} (신고 {report_id})"
        )

    result = None
    agreed = None
    if apply:
        human = (agency_id.strip(), attr_type, new_value.strip(), effective_date)
        ai = (
            report.ai_agency_id,
            report.ai_attr_type,
            report.ai_new_value,
            report.ai_effective_date,
        )
        if report.verified:
            agreed = human == ai
        # AI 해석과 다른 값으로 적용하면 사유가 있어야 한다(25). 정정을 적용하기 전에 막는다.
        require_reason(
            agreed, reason, ai_output=_describe(*ai), human=_describe(*human)
        )
        result = apply_master_change(
            session,
            human[0],
            attr_type=attr_type,
            new_value=human[2],
            effective_date=effective_date,
            reported_text=report.raw_text,
            actor=actor,
            role=role,
        )
        report.change_id = result.change.change_id
    report.status = ReportStatus.APPLIED if apply else ReportStatus.DISMISSED
    report.decision_reason = reason.strip() or None
    report.decided_by = actor
    report.decided_at = func.now()
    report.agreed = agreed
    session.flush()
    return report, result
