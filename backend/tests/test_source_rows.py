"""원본 행 모델 테스트: NONE 처리, 타입 변환, 빈 값 · 형식 오류 거부, 읽기 전용."""

import pytest
from pydantic import ValidationError

from app.seed.source_rows import AgencyRow, ArAgingRow, RebatePaymentRow

SOURCE = {"source_file": "test.csv", "source_row": 2}


def rebate(**overrides):
    """6월분 미지급 장려금 한 행(RB-00006)을 원본 글자 그대로 만든다."""
    values = {
        "rebate_id": "RB-00006",
        "agency_id": "D-001",
        "period_ym": "2026-06",
        "sales_performance_krw": "8887751",
        "rebate_amount_krw": "988932",
        "approval_status": "미지급",
        "approver": "NONE",
        "payment_date": "NONE",
        **SOURCE,
    }
    values.update(overrides)
    return RebatePaymentRow.model_validate(values)


def test_none_marker_becomes_none_not_zero():
    """NONE 은 0 이 아니라 None(해당 없음)이다."""
    row = rebate()
    assert row.approver is None
    assert row.payment_date is None


def test_strings_are_converted_to_types():
    """금액은 정수, 참거짓은 bool, 날짜는 date 로 바뀐다."""
    row = AgencyRow.model_validate(
        {
            "agency_id": "D-005",
            "agency_name": "금강상사5",
            "representative_name": "전준호",
            "business_reg_no": "244-61-86245",
            "address": "인천시 대학로 269",
            "bank_account_no": "국민 865-10-920625",
            "rebate_eligible": "False",
            "registered_date": "2020-12-16",
            **SOURCE,
        }
    )
    assert row.rebate_eligible is False
    assert row.registered_date.isoformat() == "2020-12-16"
    assert rebate().rebate_amount_krw == 988932


def test_provenance_defaults_to_original():
    """원본 행은 출처 표기가 [원본] 이다."""
    assert rebate().provenance == "원본"


def test_empty_string_is_rejected():
    """원본에 빈 칸은 없다. 빈 값은 조용히 넘기지 않는다."""
    with pytest.raises(ValidationError):
        rebate(approval_status="")
    with pytest.raises(ValidationError):
        rebate(approver="")


def test_bad_values_are_rejected():
    """금액에 글자, 잘못된 연-월 모양은 거부한다."""
    with pytest.raises(ValidationError):
        rebate(rebate_amount_krw="12a")
    with pytest.raises(ValidationError):
        rebate(period_ym="2026-6")


def test_unknown_column_is_rejected():
    """원본에 없는 컬럼이 들어오면 거부한다."""
    with pytest.raises(ValidationError):
        rebate(memo="추가 컬럼")


def test_row_is_read_only():
    """원본 값은 읽은 뒤 바꿀 수 없다."""
    row = rebate()
    with pytest.raises(ValidationError):
        row.rebate_amount_krw = 0


def test_ar_row_allows_agency_or_customer_to_be_none():
    """미수채권은 대리점 채권이면 고객이, 고객 채권이면 대리점이 NONE 이다."""
    row = ArAgingRow.model_validate(
        {
            "ar_id": "AR-C00001",
            "agency_id": "NONE",
            "customer_id": "C-101",
            "invoice_date": "2026-01-20",
            "due_date": "2026-03-21",
            "amount_krw": "12917156689",
            "outstanding_krw": "2455189033",
            "aging_days": "101",
            **SOURCE,
        }
    )
    assert row.agency_id is None
    assert row.customer_id == "C-101"
    assert row.amount_krw == 12917156689
