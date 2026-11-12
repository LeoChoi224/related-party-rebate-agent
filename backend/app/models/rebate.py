"""판매장려금 건.

RebateClaim: 월 장려금 1건(sales_rebate_payment_cv) [원본].
업무 상태(status)의 유일한 기준이다. 원본 값은 original_* 컬럼에 그대로 남긴다.
최소 결재권자와 판정 당시 그룹·합산액 컬럼은 한도 판정을 하는 06 에서 더한다.
"""

from datetime import date

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RebateClaim(Base):
    __tablename__ = "rebate_claim"

    rebate_id: Mapped[str] = mapped_column(primary_key=True)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agency.agency_id"))
    # 월 단위 키 "2026-06". 날짜로 바꾸면 없는 '1일'을 지어내게 된다.
    period_ym: Mapped[str]
    sales_performance_krw: Mapped[int]
    rebate_amount_krw: Mapped[int]
    status: Mapped[str]
    original_status: Mapped[str]
    original_approver: Mapped[str | None]
    original_payment_date: Mapped[date | None]
    source_file: Mapped[str]
    source_row: Mapped[int]
