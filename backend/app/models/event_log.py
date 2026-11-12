"""이벤트 이력.

EventLog: 누가, 언제, 무엇을, 이전 상태에서 어떤 상태로, 왜 바꿨는지 남긴다.
지금은 장려금 건 상태 전이만 남기고, 쓰는 곳은 services/claim_state.py 하나다.
다른 대상(작업 · 정정 신고)은 그 기능을 만드는 브랜치에서 entity_type 을 늘린다.
"""

from datetime import datetime

from sqlalchemy import JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EventLog(Base):
    __tablename__ = "event_log"

    event_id: Mapped[int] = mapped_column(primary_key=True)
    # SQLite CURRENT_TIMESTAMP 라 UTC 로 저장된다.
    ts: Mapped[datetime] = mapped_column(server_default=func.now())
    # 사람 이름 또는 "시스템". 역할 목록 enum 은 권한을 검사하는 09 · 12 에서 만든다.
    actor: Mapped[str]
    actor_role: Mapped[str]
    # 대상이 여러 표일 수 있어 외래키 대신 "종류 + ID" 로 가리킨다.
    entity_type: Mapped[str]
    entity_id: Mapped[str]
    from_status: Mapped[str]
    to_status: Mapped[str]
    reason: Mapped[str]
    # 전이와 함께 남길 숫자(그룹 합산액 · 최소 결재권자 등).
    payload: Mapped[dict | None] = mapped_column(JSON)
