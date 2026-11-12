"""시더 테스트: 원본으로 채운 행 수 · 기준 숫자 · 상태 변환 · 식별속성, 그리고 원본 오류 때 기존 DB 보존."""

import logging
import shutil
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import RAW_DATA_DIR
from app.core.database import make_engine
from app.models import ARItem, IdentityAttribute, RebateClaim
from app.seed.csv_loader import (
    AGENCY_CSV,
    AR_AGING_CSV,
    DEPOSIT_CSV,
    REBATE_PAYMENT_CSV,
    SourceDataError,
)
from app.seed.seeder import reset_database

EXPECTED_COUNTS = {
    "agency": 50,
    "ar_item": 146,
    "deposit": 32,
    "rebate_claim": 240,
    "identity_attr": 182,
    "group_version": 1,
    "related_group": 1,
    "group_member": 3,
    "relation_edge": 4,
    "event_log": 0,
    "approval_request": 0,
    "approval_item": 0,
}
G1 = ("D-011", "D-024", "D-037")


def count_claims(engine) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(RebateClaim))


def copy_raw(dst):
    """원본 4개 파일만 같은 폴더 구조로 복사한다. 원본 폴더는 읽기 전용이다."""
    for rel in (AGENCY_CSV, AR_AGING_CSV, DEPOSIT_CSV, REBATE_PAYMENT_CSV):
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(RAW_DATA_DIR / rel, target)
    return dst


def test_reset_returns_row_counts(tmp_path):
    """초기화 결과의 행 수가 원본과 같고, DB 에도 그만큼 들어 있다."""
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    assert reset_database(engine) == EXPECTED_COUNTS
    assert count_claims(engine) == 240
    engine.dispose()


def test_g1_june_sum_matches_source(seeded_engine):
    """G1 6월분 합산은 3,888,097원이다(영업임원 상신 기준)."""
    with Session(seeded_engine) as session:
        total = session.scalar(
            select(func.sum(RebateClaim.rebate_amount_krw)).where(
                RebateClaim.period_ym == "2026-06", RebateClaim.agency_id.in_(G1)
            )
        )
    assert total == 3_888_097


def test_status_comes_from_original_status(seeded_engine):
    """승인→지급완료, 반려→반려, 미지급→미접수. 원본 상태는 그대로 남는다."""
    with Session(seeded_engine) as session:
        pairs = session.execute(
            select(RebateClaim.original_status, RebateClaim.status, func.count())
            .group_by(RebateClaim.original_status, RebateClaim.status)
            .order_by(RebateClaim.original_status)
        ).all()
    assert [tuple(p) for p in pairs] == [
        ("미지급", "미접수", 40),
        ("반려", "반려", 4),
        ("승인", "지급완료", 196),
    ]


def test_original_none_values_are_kept_as_null(seeded_engine):
    """원본의 NONE 은 0 이나 빈 문자열이 아니라 NULL 로 남는다."""
    with Session(seeded_engine) as session:
        no_approver = session.scalar(
            select(func.count()).where(RebateClaim.original_approver.is_(None))
        )
        no_payment = session.scalar(
            select(func.count()).where(RebateClaim.original_payment_date.is_(None))
        )
        customer_ar = session.scalar(
            select(func.count()).where(ARItem.agency_id.is_(None))
        )
    assert (no_approver, no_payment, customer_ar) == (40, 44, 72)


def test_identity_attributes_per_type(seeded_engine):
    """대리점마다 3행, 입금마다 1행. 모두 [원본] 이고 아직 닫히지 않았다."""
    with Session(seeded_engine) as session:
        by_type = dict(
            session.execute(
                select(IdentityAttribute.attr_type, func.count()).group_by(
                    IdentityAttribute.attr_type
                )
            ).all()
        )
        provenances = set(session.scalars(select(IdentityAttribute.provenance)))
        closed = session.scalar(
            select(func.count()).where(IdentityAttribute.valid_to.is_not(None))
        )
    assert by_type == {"대표자": 50, "주소": 50, "등록계좌": 50, "실입금계좌": 32}
    assert provenances == {"원본"}
    assert closed == 0


def test_g1_shared_deposit_account_keeps_each_source_row(seeded_engine):
    """D-024 의 G1 공유계좌 입금 2건이 원본 14·15행 근거로 따로 남는다."""
    with Session(seeded_engine) as session:
        attrs = session.scalars(
            select(IdentityAttribute)
            .where(
                IdentityAttribute.agency_id == "D-024",
                IdentityAttribute.attr_type == "실입금계좌",
            )
            .order_by(IdentityAttribute.id)
        ).all()
    assert [a.value for a in attrs] == ["국민 412-27-556310"] * 2
    assert [a.source_ref for a in attrs] == [f"{DEPOSIT_CSV}:14", f"{DEPOSIT_CSV}:15"]
    assert all(isinstance(a.valid_from, date) for a in attrs)


def test_reset_twice_gives_same_result(seeded_engine):
    """두 번 초기화해도 행이 쌓이지 않고 같은 결과가 나온다(시연 초기화)."""
    assert reset_database(seeded_engine) == EXPECTED_COUNTS
    with Session(seeded_engine) as session:
        first_id = session.scalar(select(func.min(IdentityAttribute.id)))
    assert count_claims(seeded_engine) == 240
    assert first_id == 1


def test_unknown_status_stops_before_wiping_db(seeded_engine, tmp_path):
    """원본 상태값이 3개 밖이면 파일과 행을 알려 주며 멈추고, 기존 DB 는 그대로 둔다."""
    raw = copy_raw(tmp_path / "raw")
    path = raw / REBATE_PAYMENT_CSV
    path.write_text(
        path.read_text(encoding="utf-8").replace("|승인|", "|보류|", 1),
        encoding="utf-8",
    )
    with pytest.raises(SourceDataError, match=r"행 approval_status: .*'보류'"):
        reset_database(seeded_engine, raw_dir=raw)
    assert count_claims(seeded_engine) == 240


def test_missing_source_file_stops_before_wiping_db(seeded_engine, tmp_path):
    """원본 파일이 없으면 멈추고, 기존 DB 는 그대로 둔다."""
    with pytest.raises(FileNotFoundError, match="m_agency_cv.csv"):
        reset_database(seeded_engine, raw_dir=tmp_path / "empty")
    assert count_claims(seeded_engine) == 240


def test_reset_logs_korean_summary(tmp_path, caplog):
    """초기화가 끝나면 한글 로그에 행 수를 남긴다."""
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    with caplog.at_level(logging.INFO, logger="app.seed.seeder"):
        reset_database(engine)
    assert "업무 DB 를 원본으로 초기화했습니다" in caplog.text
    assert "'identity_attr': 182" in caplog.text
    engine.dispose()
