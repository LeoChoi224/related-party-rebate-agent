"""승인 요청(상신).

ApprovalRequest: 판정 단위(관련자 그룹 또는 한도를 넘은 단독 대리점)마다 1건.
6월분 접수(services/intake.py) 때 상신대기로 간 건을 묶어 만든다.
결정 전에는 결정 · 사유 · 결정자 · 결정 시각이 비어 있다.
AI 추천(rec_id)은 AI_RECOMMENDATION 표와 함께 17 에서 더한다.
ApprovalItem: 요청에 포함된 장려금 건.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ApprovalRequest(Base):
    __tablename__ = "approval_request"

    request_id: Mapped[int] = mapped_column(primary_key=True)
    # 단독 대리점이 한도를 넘은 경우에는 그룹이 없다.
    group_id: Mapped[int | None] = mapped_column(ForeignKey("related_group.group_id"))
    period_ym: Mapped[str]
    group_sum_krw: Mapped[int]
    approver_role: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    decision: Mapped[str | None]
    reason: Mapped[str | None]
    decided_by: Mapped[str | None]
    decided_at: Mapped[datetime | None]


class ApprovalItem(Base):
    __tablename__ = "approval_item"

    # 두 컬럼을 합친 기본키라 한 요청에 같은 건이 두 번 들어가지 않는다.
    request_id: Mapped[int] = mapped_column(
        ForeignKey("approval_request.request_id"), primary_key=True
    )
    rebate_id: Mapped[str] = mapped_column(
        ForeignKey("rebate_claim.rebate_id"), primary_key=True
    )
