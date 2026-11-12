"""초기 상태 생성.

원본 CSV 4개로 업무 DB 를 지우고 다시 채운다. 앱 시작과 시연 초기화가 같은 함수를 쓴다.
같은 원본이면 항상 같은 결과가 나와야 한다(재현성).
확장 데이터 [가정](backend/data/ext)은 그 데이터를 처음 쓰는 브랜치에서 더한다.
"""

import logging
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.config import RAW_DATA_DIR
from app.models import Agency, ARItem, Base, Deposit, IdentityAttribute, RebateClaim
from app.models.enums import ClaimStatus, IdentityAttrType
from app.seed.csv_loader import (
    AGENCY_CSV,
    AR_AGING_CSV,
    DEPOSIT_CSV,
    REBATE_PAYMENT_CSV,
    SourceDataError,
    read_source_csv,
)
from app.seed.source_rows import (
    AgencyRow,
    ArAgingRow,
    DepositRow,
    RebatePaymentRow,
    SourceRow,
)

logger = logging.getLogger(__name__)

# 원본 승인 상태 → 업무 상태 첫 값. 미지급은 아직 접수 전으로 본다 [가정].
STATUS_FROM_ORIGINAL = {
    "승인": ClaimStatus.PAID,
    "반려": ClaimStatus.REJECTED,
    "미지급": ClaimStatus.NOT_RECEIVED,
}


def reset_database(engine: Engine, raw_dir: Path = RAW_DATA_DIR) -> dict[str, int]:
    """원본으로 업무 DB 를 처음 상태로 되돌리고, 표 이름별 행 수를 돌려준다."""
    # 원본이 틀려서 멈출 때 기존 DB 를 지우기 전에 멈추도록, 읽기와 변환을 먼저 끝낸다.
    agency_rows = read_source_csv(AGENCY_CSV, AgencyRow, raw_dir)
    ar_rows = read_source_csv(AR_AGING_CSV, ArAgingRow, raw_dir)
    deposit_rows = read_source_csv(DEPOSIT_CSV, DepositRow, raw_dir)
    rebate_rows = read_source_csv(REBATE_PAYMENT_CSV, RebatePaymentRow, raw_dir)

    # 외래키 순서(부모 표 먼저). relationship 이 없어 SQLAlchemy 가 순서를 정해 주지 않는다.
    tables = [
        (Agency, [Agency(**_columns(row)) for row in agency_rows]),
        (ARItem, [ARItem(**_columns(row)) for row in ar_rows]),
        (Deposit, [Deposit(**_columns(row)) for row in deposit_rows]),
        (RebateClaim, [_to_claim(row) for row in rebate_rows]),
        (IdentityAttribute, _identity_attributes(agency_rows, deposit_rows)),
    ]

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        for _, objects in tables:
            session.add_all(objects)
            # 다음 표가 가리킬 부모 행을 DB 에 먼저 넣어 외래키 검사를 통과시킨다.
            session.flush()

    counts = {model.__tablename__: len(objects) for model, objects in tables}
    logger.info("업무 DB 를 원본으로 초기화했습니다: %s", counts)
    return counts


def _columns(row: SourceRow) -> dict:
    """03 에서 컬럼 이름을 원본 헤더 그대로 뒀으므로, 컬럼이 없는 출처 표기만 뺀다."""
    return row.model_dump(exclude={"provenance"})


def _source_ref(row: SourceRow) -> str:
    return f"{row.source_file}:{row.source_row}"


def _to_claim(row: RebatePaymentRow) -> RebateClaim:
    status = STATUS_FROM_ORIGINAL.get(row.approval_status)
    if status is None:
        # 조용히 기본값을 넣으면 잘못된 상태가 업무 DB 에 남는다.
        raise SourceDataError(
            f"{row.source_file} {row.source_row}행 approval_status: "
            f"알 수 없는 상태입니다 '{row.approval_status}'"
        )
    return RebateClaim(
        rebate_id=row.rebate_id,
        agency_id=row.agency_id,
        period_ym=row.period_ym,
        sales_performance_krw=row.sales_performance_krw,
        rebate_amount_krw=row.rebate_amount_krw,
        status=status,
        original_status=row.approval_status,
        original_approver=row.approver,
        original_payment_date=row.payment_date,
        source_file=row.source_file,
        source_row=row.source_row,
    )


def _identity_attributes(
    agency_rows: list[AgencyRow], deposit_rows: list[DepositRow]
) -> list[IdentityAttribute]:
    """대리점마다 대표자·주소·등록계좌 3행, 입금마다 실입금계좌 1행."""
    attrs = []
    for row in agency_rows:
        for attr_type, value in (
            (IdentityAttrType.REPRESENTATIVE, row.representative_name),
            (IdentityAttrType.ADDRESS, row.address),
            (IdentityAttrType.REGISTERED_ACCOUNT, row.bank_account_no),
        ):
            attrs.append(
                IdentityAttribute(
                    agency_id=row.agency_id,
                    attr_type=attr_type,
                    value=value,
                    provenance=row.provenance,
                    source_ref=_source_ref(row),
                    valid_from=row.registered_date,
                )
            )
    # 같은 계좌라도 입금마다 따로 남긴다. 판정 근거로 입금 행을 하나씩 보여 줘야 한다.
    for row in deposit_rows:
        attrs.append(
            IdentityAttribute(
                agency_id=row.agency_id,
                attr_type=IdentityAttrType.DEPOSIT_ACCOUNT,
                value=row.bank_account_no,
                provenance=row.provenance,
                source_ref=_source_ref(row),
                valid_from=row.deposit_date,
            )
        )
    return attrs
