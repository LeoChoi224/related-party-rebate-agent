"""원본 CSV 한 행의 모양(계약).

컬럼 이름은 원본 헤더 그대로 두고, NONE 은 None 으로, 행마다 출처를 붙인다.
04 DB 모델과 05 관련자 판정 엔진이 이 모양을 믿고 쓴다.
"""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints


def _none_marker(value: object) -> object:
    """원본의 NONE(해당 없음)을 None 으로 바꾼다. 0 과는 다른 값이다."""
    return None if value == "NONE" else value


NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
OptionalStr = Annotated[NonEmptyStr | None, BeforeValidator(_none_marker)]
OptionalDate = Annotated[date | None, BeforeValidator(_none_marker)]
# 월 단위 키. 날짜로 바꾸면 없는 '1일'을 지어내게 된다.
YearMonth = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}$")]


class SourceRow(BaseModel):
    """모든 원본 행의 공통 부분: 어느 파일 몇 번째 줄에서 왔는지."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_file: str
    source_row: int
    provenance: str = "원본"


class AgencyRow(SourceRow):
    """대리점 마스터 (m_agency_cv.csv)."""

    agency_id: NonEmptyStr
    agency_name: NonEmptyStr
    representative_name: NonEmptyStr
    business_reg_no: NonEmptyStr
    address: NonEmptyStr
    bank_account_no: NonEmptyStr
    rebate_eligible: bool
    registered_date: date


class RebatePaymentRow(SourceRow):
    """판매장려금 지급 (sales_rebate_payment_cv.csv)."""

    rebate_id: NonEmptyStr
    agency_id: NonEmptyStr
    period_ym: YearMonth
    sales_performance_krw: int
    rebate_amount_krw: int
    approval_status: NonEmptyStr
    approver: OptionalStr
    payment_date: OptionalDate


class DepositRow(SourceRow):
    """실제 입금 기록 (fin_collection_history_cv.csv)."""

    deposit_id: NonEmptyStr
    agency_id: NonEmptyStr
    deposit_date: date
    amount_krw: int
    bank_account_no: NonEmptyStr
    matched_ar_id: NonEmptyStr


class ArAgingRow(SourceRow):
    """미수채권 (fin_ar_aging_cv.csv). 대리점 채권과 고객 채권이 섞여 있다."""

    ar_id: NonEmptyStr
    agency_id: OptionalStr
    customer_id: OptionalStr
    invoice_date: date
    due_date: date
    amount_krw: int
    outstanding_krw: int
    aging_days: int
