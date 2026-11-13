"""미수채권과 상계 조정.

ARItem: 미수채권(fin_ar_aging_cv) [원본]. 대리점 채권 74행과 고객 채권 72행을 모두 담는다.
원본 잔액(outstanding_krw)은 수정하지 않는다.
ARAdjustment: 상계로 줄어든 금액 [가정]. 지금 잔액 = 원본 잔액 - 조정 합계.
"""

from datetime import date, datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ARItem(Base):
    __tablename__ = "ar_item"

    ar_id: Mapped[str] = mapped_column(primary_key=True)
    # 고객 채권이면 agency_id 가 비고 customer_id 만 있다.
    agency_id: Mapped[str | None] = mapped_column(ForeignKey("agency.agency_id"))
    customer_id: Mapped[str | None]
    invoice_date: Mapped[date]
    due_date: Mapped[date]
    amount_krw: Mapped[int]
    outstanding_krw: Mapped[int]
    aging_days: Mapped[int]
    source_file: Mapped[str]
    source_row: Mapped[int]


class ARAdjustment(Base):
    __tablename__ = "ar_adjustment"

    id: Mapped[int] = mapped_column(primary_key=True)
    ar_id: Mapped[str] = mapped_column(ForeignKey("ar_item.ar_id"))
    offset_id: Mapped[int] = mapped_column(ForeignKey("offset_proposal.offset_id"))
    amount_krw: Mapped[int]
    provenance: Mapped[str]
    applied_at: Mapped[datetime] = mapped_column(server_default=func.now())
