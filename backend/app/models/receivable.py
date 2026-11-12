"""미수채권.

ARItem: 미수채권(fin_ar_aging_cv) [원본]. 대리점 채권 74행과 고객 채권 72행을 모두 담는다.
원본 잔액은 수정하지 않는다.
상계로 줄어든 금액을 남기는 ARAdjustment [가정]는 22(상계)에서 추가한다.
"""

from datetime import date

from sqlalchemy import ForeignKey
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
