"""원본 로더 테스트: 실제 원본 4개 파일의 행 수 · 출처 · NONE 개수, 그리고 파일 · 헤더 · 값 오류."""

import pytest

from app.seed.csv_loader import (
    AGENCY_CSV,
    AR_AGING_CSV,
    DEPOSIT_CSV,
    REBATE_PAYMENT_CSV,
    SourceDataError,
    read_source_csv,
)
from app.seed.source_rows import AgencyRow, ArAgingRow, DepositRow, RebatePaymentRow

DEPOSIT_HEADER = (
    "deposit_id|agency_id|deposit_date|amount_krw|bank_account_no|matched_ar_id"
)
DEPOSIT_LINE = "DP-00001|D-001|2026-06-03|20861742|기업 198-22-851114|AR-D00073"


@pytest.mark.parametrize(
    ("relative_path", "row_model", "count"),
    [
        (AGENCY_CSV, AgencyRow, 50),
        (REBATE_PAYMENT_CSV, RebatePaymentRow, 240),
        (DEPOSIT_CSV, DepositRow, 32),
        (AR_AGING_CSV, ArAgingRow, 146),
    ],
)
def test_original_files_load_with_expected_row_counts(relative_path, row_model, count):
    """원본 4개 파일이 모두 읽히고 행 수가 원본과 같다."""
    assert len(read_source_csv(relative_path, row_model)) == count


def test_each_row_records_its_source_file_and_line():
    """첫 데이터 행은 파일의 2행(헤더가 1행)이고, 출처는 [원본] 이다."""
    rows = read_source_csv(REBATE_PAYMENT_CSV, RebatePaymentRow)
    assert rows[0].source_file == REBATE_PAYMENT_CSV
    assert rows[0].source_row == 2
    assert rows[-1].source_row == 241
    assert rows[0].provenance == "원본"


def test_none_markers_in_original_data_become_none():
    """원본의 NONE 개수가 그대로 None 개수가 된다."""
    rebates = read_source_csv(REBATE_PAYMENT_CSV, RebatePaymentRow)
    assert sum(r.approver is None for r in rebates) == 40
    assert sum(r.payment_date is None for r in rebates) == 44

    ar = read_source_csv(AR_AGING_CSV, ArAgingRow)
    assert sum(r.agency_id is not None for r in ar) == 74
    assert sum(r.customer_id is not None for r in ar) == 72


def test_missing_file_raises_with_path(tmp_path):
    """파일이 없으면 어느 파일인지 알려준다."""
    with pytest.raises(FileNotFoundError, match="nope.csv"):
        read_source_csv("nope.csv", DepositRow, base_dir=tmp_path)


def write_csv(tmp_path, *lines):
    (tmp_path / "deposit.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_header_mismatch_is_rejected(tmp_path):
    """컬럼 이름이 바뀌면 바로 멈춘다."""
    write_csv(tmp_path, DEPOSIT_HEADER.replace("amount_krw", "amount"), DEPOSIT_LINE)
    with pytest.raises(SourceDataError, match="헤더"):
        read_source_csv("deposit.csv", DepositRow, base_dir=tmp_path)


def test_empty_file_is_rejected(tmp_path):
    """빈 파일은 헤더가 없으므로 거부한다."""
    write_csv(tmp_path)
    with pytest.raises(SourceDataError, match="헤더"):
        read_source_csv("deposit.csv", DepositRow, base_dir=tmp_path)


def test_short_row_is_rejected_not_read_as_none(tmp_path):
    """칸이 모자란 줄은 NONE 처럼 통과하지 않고 몇 행인지 알려준다."""
    short = DEPOSIT_LINE.rsplit("|", 1)[0]
    write_csv(tmp_path, DEPOSIT_HEADER, DEPOSIT_LINE, short)
    with pytest.raises(SourceDataError, match="3행: 열 개수"):
        read_source_csv("deposit.csv", DepositRow, base_dir=tmp_path)


def test_long_row_is_rejected(tmp_path):
    """칸이 남는 줄도 거부한다."""
    write_csv(tmp_path, DEPOSIT_HEADER, DEPOSIT_LINE + "|추가")
    with pytest.raises(SourceDataError, match="2행: 열 개수"):
        read_source_csv("deposit.csv", DepositRow, base_dir=tmp_path)


def test_bad_value_reports_line_and_column(tmp_path):
    """값이 형식에 안 맞으면 몇 행 어느 컬럼인지 알려준다."""
    bad = DEPOSIT_LINE.replace("20861742", "2천만원")
    write_csv(tmp_path, DEPOSIT_HEADER, bad)
    with pytest.raises(SourceDataError, match="2행 amount_krw"):
        read_source_csv("deposit.csv", DepositRow, base_dir=tmp_path)
