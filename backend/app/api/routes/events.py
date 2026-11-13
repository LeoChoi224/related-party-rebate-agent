"""이벤트 이력 API: 모든 건의 상태 전이를 최신순으로.

AI 추천 기록 · 일치율은 AI 추천이 생기는 17 · 25 에서 더한다.
"""

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import SessionDep
from app.models import EventLog
from app.schemas.event_log import EventLogOut

router = APIRouter(prefix="/events", tags=["events"])


# 접두사 /events 자체가 목록 주소다. "/" 로 두면 /api/events 가 307 로 한 번 더 돈다.
@router.get("")
def list_events(
    session: SessionDep,
    rebate_id: str | None = None,
    # 처리자 역할에는 결재 역할 말고도 "시스템"(접수) · "모의 외부"(은행)가 있어 문자열로 받는다.
    actor_role: str | None = None,
) -> list[EventLogOut]:
    """상태 전이 이력. 같은 초에 여러 줄이 찍히므로 시각이 아니라 ID 내림차순이다.

    없는 건 · 역할은 빈 목록이다(거르기 조건이지 건 하나를 찾는 주소가 아니다).
    """
    query = select(EventLog).order_by(EventLog.event_id.desc())
    if rebate_id:
        query = query.where(
            EventLog.entity_type == "rebate_claim", EventLog.entity_id == rebate_id
        )
    if actor_role:
        query = query.where(EventLog.actor_role == actor_role)
    return session.scalars(query).all()
