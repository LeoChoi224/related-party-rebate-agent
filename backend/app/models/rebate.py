"""판매장려금 건.

RebateClaim: 월 장려금 1건(sales_rebate_payment_cv) [원본].
업무 상태(status)의 유일한 기준이다. 원본 값은 original_* 컬럼에 그대로 남긴다.
min_authority · group_id · group_sum_krw 는 한도 판정(services/approval_authority.py)이 채운다.
비어 있으면 아직 판정 전이다.
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
    # 규정상 최소 결재권자. 시더는 채우지 않는다.
    min_authority: Mapped[str | None]
    # 판정 당시 그룹. 단독 대리점이면 판정 뒤에도 비어 있다.
    group_id: Mapped[int | None] = mapped_column(ForeignKey("related_group.group_id"))
    # 판정 단위(그룹 또는 단독 대리점)의 그 달 합산. 반려 건은 빠진다.
    group_sum_krw: Mapped[int | None]
    original_status: Mapped[str]
    original_approver: Mapped[str | None]
    original_payment_date: Mapped[date | None]
    source_file: Mapped[str]
    source_row: Mapped[int]
