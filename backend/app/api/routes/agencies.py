"""마스터 정정 신고 API: 정정 신고 적용(그룹 재계산 · 영향 건 재판정), 정정 이력 조회,
신고 문장 AI 해석과 영업지원팀 확인(19).

권한 부족(403) · 상태 충돌(409) · AI 와 다른 값에 사유 없음(422)은 main.py 의 처리기가 바꾸고,
요청 트랜잭션은 롤백된다. 확인은 서비스가 정정을 적용한 뒤에만 기다리는 해석 그래프를 재개한다(17).
"""

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.agents.graphs.master_change_parser import (
    record_human_confirmation,
    start_parse,
)
from app.api.deps import ReviewModelDep, SessionDep
from app.models import MasterChange, MasterChangeReport
from app.schemas.master_change import (
    MasterChangeOut,
    MasterChangeRequest,
    MasterChangeResult,
    ReportCreate,
    ReportDecision,
    ReportDecisionResult,
    ReportOut,
)
from app.services.master_change import InvalidMasterChangeError, apply_master_change
from app.services.master_change_report import create_report, decide_report

router = APIRouter(tags=["master-changes"])


@router.post(
    "/agencies/{agency_id}/master-changes",
    responses={
        403: {"description": "영업지원팀이 아님"},
        404: {"description": "대리점이 없음"},
        422: {
            "description": "정정할 수 없는 신고(같은 값 · 빈 값 · 정정일 오류 · 실입금계좌)"
        },
    },
)
def report_master_change(
    agency_id: str, body: MasterChangeRequest, session: SessionDep
) -> MasterChangeResult:
    """대표자 · 주소 · 등록계좌 정정을 적용한다. 그룹이 새 버전으로 다시 계산되고 영향받는 건이 다시 판정된다."""
    try:
        return apply_master_change(
            session,
            agency_id,
            attr_type=body.attr_type,
            new_value=body.new_value,
            effective_date=body.effective_date,
            reported_text=body.reported_text,
            actor=body.actor,
            role=body.role,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except InvalidMasterChangeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/master-changes")
def list_master_changes(session: SessionDep) -> list[MasterChangeOut]:
    """정정 신고 이력(최신순)."""
    changes = session.scalars(
        select(MasterChange).order_by(MasterChange.change_id.desc())
    ).all()
    return [MasterChangeOut.model_validate(c) for c in changes]


@router.post(
    "/master-change-reports",
    responses={
        403: {"description": "영업지원팀이 아님"},
        422: {"description": "빈 신고 문장"},
    },
)
def create_master_change_report(
    body: ReportCreate, request: Request, session: SessionDep, model: ReviewModelDep
) -> ReportOut:
    """신고 문장을 받아 AI 가 대리점 · 속성 · 새 값으로 해석한다(19). 적용은 확인 API 에서 사람이 한다."""
    report = create_report(session, body.raw_text, actor=body.actor, role=body.role)
    start_parse(session, request.app.state.checkpointer, model, report)
    return ReportOut.model_validate(report)


@router.post(
    "/master-change-reports/{report_id}/decision",
    responses={
        403: {"description": "영업지원팀이 아님"},
        404: {"description": "신고 문장 · 대리점이 없음"},
        409: {"description": "이미 확인한 신고"},
        422: {
            "description": "빠진 값 · 정정할 수 없는 값 · AI 해석과 다른 값에 사유 없음"
        },
    },
)
def decide_master_change_report(
    report_id: int, body: ReportDecision, request: Request, session: SessionDep
) -> ReportDecisionResult:
    """영업지원팀이 해석을 확인 · 수정해 정정을 적용하거나 신고를 기각한다."""
    try:
        report, result = decide_report(
            session,
            report_id,
            apply=body.apply,
            agency_id=body.agency_id,
            attr_type=body.attr_type,
            new_value=body.new_value,
            effective_date=body.effective_date,
            reason=body.reason,
            actor=body.actor,
            role=body.role,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except InvalidMasterChangeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    # 검사를 통과하고 적용까지 끝난 확인만 그래프에 넣는다(17 · 18 과 같은 순서).
    record_human_confirmation(
        session,
        request.app.state.checkpointer,
        report_id,
        apply=body.apply,
        actor=body.actor,
    )
    return ReportDecisionResult(report=ReportOut.model_validate(report), result=result)


@router.get("/master-change-reports")
def list_master_change_reports(session: SessionDep) -> list[ReportOut]:
    """신고 문장과 AI 해석 · 확인 기록(최신순)."""
    reports = session.scalars(
        select(MasterChangeReport).order_by(MasterChangeReport.report_id.desc())
    ).all()
    return [ReportOut.model_validate(r) for r in reports]
