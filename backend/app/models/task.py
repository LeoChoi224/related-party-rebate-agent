"""부서별 작업.

Task: 장려금 건의 상태가 바뀔 때 규칙표(services/task_dispatcher.py)로 자동 생기는 할 일.
건이 그 상태를 떠나면 그 상태(trigger_status)가 만든 열린 작업은 자동으로 완료된다.
상태 전이가 아닌 작업(접수 때 정황 소명 요청 · 24 의 감사 사후 검토)은
trigger_status 와 created_by_event 가 비어 있다.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Task(Base):
    __tablename__ = "task"

    task_id: Mapped[int] = mapped_column(primary_key=True)
    dept: Mapped[str]
    task_type: Mapped[str]
    # 대상이 여러 표일 수 있어 외래키 대신 "종류 + ID" 로 가리킨다(EventLog 와 같음).
    ref_type: Mapped[str]
    ref_id: Mapped[str]
    status: Mapped[str]
    trigger_status: Mapped[str | None]
    # 작업 목록에서 "왜 이 일이 왔나"가 먼저 보여야 해서 비울 수 없다.
    detail: Mapped[str]
    created_by_event: Mapped[int | None] = mapped_column(
        ForeignKey("event_log.event_id")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    closed_at: Mapped[datetime | None]
