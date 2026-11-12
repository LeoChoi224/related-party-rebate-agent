"""원본 CSV 로더.

파이프(|) 구분, UTF-8, 첫 행 헤더. NONE은 0이 아니라 '해당 없음'으로 읽는다.
모든 행에 출처(파일명, 행 번호, [원본] 표기)를 붙인다.
파일을 읽어 source_rows 모델 목록으로 바꿀 뿐, DB 는 모른다.
"""

import csv
from pathlib import Path

from pydantic import ValidationError

from app.core.config import RAW_DATA_DIR
from app.seed.source_rows import SourceRow

AGENCY_CSV = "01_corevia/master/m_agency_cv.csv"
REBATE_PAYMENT_CSV = "01_corevia/sales/sales_rebate_payment_cv.csv"
DEPOSIT_CSV = "01_corevia/financials/fin_collection_history_cv.csv"
AR_AGING_CSV = "01_corevia/financials/fin_ar_aging_cv.csv"


class SourceDataError(ValueError):
    """원본 파일의 헤더 · 열 개수 · 값이 계약(source_rows)과 다를 때."""


def read_source_csv[T: SourceRow](
    relative_path: str, row_model: type[T], base_dir: Path = RAW_DATA_DIR
) -> list[T]:
    path = base_dir / relative_path
    if not path.is_file():
        raise FileNotFoundError(f"원본 파일이 없습니다: {path}")

    # 출처 필드(source_file 등)를 뺀 나머지가 원본 헤더와 같은 순서여야 한다.
    expected = [
        name for name in row_model.model_fields if name not in SourceRow.model_fields
    ]
    rows: list[T] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="|")
        if reader.fieldnames != expected:
            raise SourceDataError(
                f"{relative_path}: 헤더가 다릅니다. "
                f"기대 {expected}, 실제 {reader.fieldnames}"
            )
        for raw in reader:
            line = reader.line_num
            # 칸이 많으면 키 None, 적으면 값 None 이 생긴다.
            # 빠진 칸이 NONE 처럼 조용히 통과하지 않게 Pydantic 보다 먼저 막는다.
            if None in raw or None in raw.values():
                raise SourceDataError(
                    f"{relative_path} {line}행: 열 개수가 헤더와 다릅니다"
                )
            try:
                row = row_model.model_validate(
                    {**raw, "source_file": relative_path, "source_row": line}
                )
            except ValidationError as e:
                err = e.errors()[0]
                column = ".".join(str(part) for part in err["loc"])
                raise SourceDataError(
                    f"{relative_path} {line}행 {column}: {err['msg']}"
                ) from e
            rows.append(row)
    return rows
