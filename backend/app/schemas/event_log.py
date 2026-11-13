"""이벤트 이력 한 줄 응답."""

from pydantic import BaseModel, ConfigDict

from app.schemas.common import UtcDatetime


class EventLogOut(BaseModel):
    """건 상태 전이 한 줄. 라우트 · 서비스가 ORM 객체(EventLog)를 그대로 넘기면 속성을 읽어 만든다."""

    model_config = ConfigDict(from_attributes=True)

    event_id: int
    ts: UtcDatetime
    actor: str
    actor_role: str
    from_status: str
    to_status: str
    reason: str
    payload: dict | None
