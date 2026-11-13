"""마스터 정정 신고 API: 정정 신고 적용(그룹 재계산 · 영향 건 재판정), 정정 이력 조회.

권한 부족(403)은 main.py 의 처리기가 바꾸고, 요청 트랜잭션은 롤백된다.
정정 문장을 AI 가 해석하는 master_change_parser(19)는 이 API 에 구조화된 값을 넘기는 앞단이 된다.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import SessionDep
from app.models import MasterChange
from app.schemas.master_change import (
    MasterChangeOut,
    MasterChangeRequest,
    MasterChangeResult,
)
from app.services.master_change import InvalidMasterChangeError, apply_master_change

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
