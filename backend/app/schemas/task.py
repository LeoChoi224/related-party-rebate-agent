"""부서별 작업 응답과 작업 상태 변경 요청."""

from pydantic import BaseModel, ConfigDict

from app.models.enums import TaskStatus
from app.schemas.common import UtcDatetime


class TaskOut(BaseModel):
    """작업 한 건. 라우트가 ORM 객체(Task)를 그대로 돌려주면 속성을 읽어 만든다."""

    model_config = ConfigDict(from_attributes=True)

    task_id: int
    dept: str
    task_type: str
    ref_type: str
    ref_id: str
    status: str
    trigger_status: str | None
    detail: str
    created_by_event: int | None
    created_at: UtcDatetime
    closed_at: UtcDatetime | None


class TaskStatusChange(BaseModel):
    status: TaskStatus
