"""대리점과 식별정보.

Agency: 대리점 마스터(m_agency_cv) [원본].
IdentityAttribute: 대표자·주소·등록계좌·실입금계좌. 정정되면 유효기간을 닫고 새 행을 만든다.
Deposit: 실제 입금 기록(fin_collection_history_cv) [원본]. 실입금계좌 대조에 쓴다.
"""

from datetime import date

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Agency(Base):
    __tablename__ = "agency"

    agency_id: Mapped[str] = mapped_column(primary_key=True)
    agency_name: Mapped[str]
    representative_name: Mapped[str]
    business_reg_no: Mapped[str]
    address: Mapped[str]
    bank_account_no: Mapped[str]
    rebate_eligible: Mapped[bool]
    registered_date: Mapped[date]
    source_file: Mapped[str]
    source_row: Mapped[int]


class IdentityAttribute(Base):
    __tablename__ = "identity_attr"

    id: Mapped[int] = mapped_column(primary_key=True)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agency.agency_id"))
    attr_type: Mapped[str]
    value: Mapped[str]
    provenance: Mapped[str]
    # "파일:행" — 판정 근거로 원본 행을 보여 줄 때 쓴다.
    source_ref: Mapped[str]
    valid_from: Mapped[date]
    # 비어 있으면 지금도 유효하다.
    valid_to: Mapped[date | None]


class Deposit(Base):
    __tablename__ = "deposit"

    deposit_id: Mapped[str] = mapped_column(primary_key=True)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agency.agency_id"))
    deposit_date: Mapped[date]
    amount_krw: Mapped[int]
    # 실제로 돈이 들어온 계좌. 등록계좌와 다를 수 있다.
    bank_account_no: Mapped[str]
    matched_ar_id: Mapped[str] = mapped_column(ForeignKey("ar_item.ar_id"))
    source_file: Mapped[str]
    source_row: Mapped[int]
