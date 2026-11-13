"""원본 5개 표 모델 테스트: 표 생성, 비어 있어도 되는 컬럼, 외래키, 한글 값 저장."""

from datetime import date

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import make_engine
from app.models import (
    Agency,
    ARItem,
    BankReply,
    Base,
    Deposit,
    IdentityAttribute,
    PaymentOrder,
    RebateClaim,
)
from app.models.enums import (
    ApproverRole,
    BankResult,
    ClaimStatus,
    Decision,
    Department,
    IdentityAttrType,
    PaymentStatus,
    Provenance,
    TaskStatus,
)


@pytest.fixture
def db_engine(tmp_path):
    """ERD 의 모든 표를 만든 임시 파일 DB."""
    eng = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def make_agency(agency_id: str = "D-011") -> Agency:
    return Agency(
        agency_id=agency_id,
        agency_name="테스트대리점",
        representative_name="홍길동",
        business_reg_no="123-45-67890",
        address="서울시 중구",
        bank_account_no="국민 412-27-556310",
        rebate_eligible=True,
        registered_date=date(2024, 1, 2),
        source_file="m_agency_cv.csv",
        source_row=12,
    )


def make_claim(agency_id: str = "D-011") -> RebateClaim:
    return RebateClaim(
        rebate_id="RB-00001",
        agency_id=agency_id,
        period_ym="2026-06",
        sales_performance_krw=10_000_000,
        rebate_amount_krw=300_000,
        status=ClaimStatus.NOT_RECEIVED,
        original_status="미지급",
        original_approver=None,
        original_payment_date=None,
        source_file="sales_rebate_payment_cv.csv",
        source_row=2,
    )


def test_create_all_makes_erd_tables(db_engine):
    """create_all 하면 지금까지 만든 ERD 표가 이름 그대로 모두 생긴다."""
    assert sorted(inspect(db_engine).get_table_names()) == [
        "agency",
        "ai_recommendation",
        "approval_item",
        "approval_request",
        "ar_adjustment",
        "ar_item",
        "bank_reply",
        "deposit",
        "event_log",
        "explanation_check",
        "explanation_reply",
        "explanation_request",
        "group_member",
        "group_version",
        "identity_attr",
        "master_change",
        "master_change_report",
        "offset_proposal",
        "payment_order",
        "rebate_claim",
        "related_group",
        "relation_edge",
        "task",
    ]


@pytest.mark.parametrize(
    ("table", "column", "nullable"),
    [
        ("ar_item", "agency_id", True),
        ("ar_item", "customer_id", True),
        ("rebate_claim", "original_approver", True),
        ("rebate_claim", "original_payment_date", True),
        ("rebate_claim", "min_authority", True),
        ("rebate_claim", "group_id", True),
        ("rebate_claim", "group_sum_krw", True),
        ("event_log", "payload", True),
        ("event_log", "from_status", False),
        ("event_log", "reason", False),
        ("approval_request", "group_id", True),
        ("approval_request", "decision", True),
        ("approval_request", "decided_at", True),
        ("approval_request", "approver_role", False),
        ("task", "trigger_status", True),
        ("task", "created_by_event", True),
        ("task", "closed_at", True),
        ("task", "detail", False),
        ("payment_order", "amount_krw", False),
        ("bank_reply", "provenance", False),
        ("identity_attr", "valid_to", True),
        ("ar_item", "outstanding_krw", False),
        ("rebate_claim", "status", False),
        ("deposit", "matched_ar_id", False),
    ],
)
def test_nullable_follows_mapped_type(db_engine, table, column, nullable):
    """`X | None` 으로 적은 컬럼만 비어 있어도 된다."""
    columns = {c["name"]: c for c in inspect(db_engine).get_columns(table)}
    assert columns[column]["nullable"] is nullable


def test_foreign_keys_point_to_parent_tables(db_engine):
    """입금은 대리점과 미수채권을, 장려금은 대리점과 판정 당시 그룹을, 나머지는 대리점을 가리킨다."""
    inspector = inspect(db_engine)

    def fk_map(table: str) -> dict[str, str]:
        return {
            fk["constrained_columns"][0]: fk["referred_table"]
            for fk in inspector.get_foreign_keys(table)
        }

    assert fk_map("deposit") == {"agency_id": "agency", "matched_ar_id": "ar_item"}
    assert fk_map("ar_item") == {"agency_id": "agency"}
    assert fk_map("rebate_claim") == {
        "agency_id": "agency",
        "group_id": "related_group",
    }
    assert fk_map("identity_attr") == {"agency_id": "agency"}
    assert fk_map("approval_request") == {"group_id": "related_group"}
    assert fk_map("approval_item") == {
        "request_id": "approval_request",
        "rebate_id": "rebate_claim",
    }
    assert fk_map("task") == {"created_by_event": "event_log"}
    assert fk_map("payment_order") == {"rebate_id": "rebate_claim"}
    assert fk_map("bank_reply") == {"payment_id": "payment_order"}


def test_rows_round_trip_with_korean_values(db_engine):
    """StrEnum 값은 이름(PAID)이 아니라 한글 값으로 저장되고, 날짜는 date 로 돌아온다."""
    with Session(db_engine) as session, session.begin():
        session.add(make_agency())
        session.flush()
        session.add_all(
            [
                ARItem(
                    ar_id="AR-C00001",
                    agency_id=None,
                    customer_id="C-001",
                    invoice_date=date(2026, 1, 5),
                    due_date=date(2026, 2, 4),
                    amount_krw=1_000_000,
                    outstanding_krw=1_000_000,
                    aging_days=146,
                    source_file="fin_ar_aging_cv.csv",
                    source_row=80,
                ),
                IdentityAttribute(
                    agency_id="D-011",
                    attr_type=IdentityAttrType.REGISTERED_ACCOUNT,
                    value="국민 412-27-556310",
                    provenance=Provenance.ORIGINAL,
                    source_ref="m_agency_cv.csv:12",
                    valid_from=date(2024, 1, 2),
                ),
                make_claim(),
            ]
        )

    with Session(db_engine) as session:
        claim = session.get(RebateClaim, "RB-00001")
        assert claim.status == ClaimStatus.NOT_RECEIVED
        assert claim.original_payment_date is None
        attr = session.scalars(select(IdentityAttribute)).one()
        assert attr.id == 1
        assert attr.valid_from == date(2024, 1, 2)
        assert attr.valid_to is None
        assert session.get(ARItem, "AR-C00001").agency_id is None

    with db_engine.connect() as conn:
        raw = conn.execute(text("SELECT status FROM rebate_claim")).scalar()
        assert raw == "미접수"


def test_claim_for_unknown_agency_is_rejected(db_engine):
    """없는 대리점의 장려금 건은 외래키 검사에 걸린다."""
    with (
        pytest.raises(IntegrityError),
        Session(db_engine) as session,
        session.begin(),
    ):
        session.add(make_claim(agency_id="D-999"))


def test_deposit_for_unknown_receivable_is_rejected(db_engine):
    """입금이 가리키는 미수채권이 없으면 저장되지 않는다."""
    with Session(db_engine) as session, session.begin():
        session.add(make_agency())
    with (
        pytest.raises(IntegrityError),
        Session(db_engine) as session,
        session.begin(),
    ):
        session.add(
            Deposit(
                deposit_id="DP-00001",
                agency_id="D-011",
                deposit_date=date(2026, 3, 2),
                amount_krw=500_000,
                bank_account_no="국민 412-27-556310",
                matched_ar_id="AR-D99999",
                source_file="fin_collection_history_cv.csv",
                source_row=2,
            )
        )


def test_bank_reply_is_one_per_payment_order(db_engine):
    """지시 하나에 회신은 하나다. 같은 지시에 두 번째 회신을 넣으면 DB 가 막는다."""
    with Session(db_engine) as session, session.begin():
        session.add(make_agency())
        session.flush()
        session.add(make_claim())
        session.flush()
        order = PaymentOrder(
            rebate_id="RB-00001", amount_krw=300_000, status="회신대기", ordered_by="t"
        )
        session.add(order)
        session.flush()
        session.add(
            BankReply(payment_id=order.payment_id, result="계좌오류", provenance="모의")
        )
    with (
        pytest.raises(IntegrityError),
        Session(db_engine) as session,
        session.begin(),
    ):
        session.add(BankReply(payment_id=1, result="성공", provenance="모의"))


def test_enum_values_match_source_labels():
    """코드 값은 원본·화면에 쓰는 한글 표기와 같다."""
    assert [s.value for s in ClaimStatus] == [
        "미접수",
        "접수",
        "관계확인",
        "전결대기",
        "상신대기",
        "소명대기",
        "지급보류",
        "승인",
        "반려",
        "상계검토",
        "지급지시",
        "지급완료",
        "상계완료",
        "재검토필요",
    ]
    assert {p.value for p in Provenance} == {"원본", "주장", "가정", "모의"}
    # 낮은 단계부터 적은 순서도 계약이다. 가드(17)가 이 순서로 높낮이를 본다.
    assert [r.value for r in ApproverRole] == ["영업지원팀", "영업임원"]
    assert [d.value for d in Decision] == ["승인", "반려"]
    # 부서는 역할 화면에서 그대로 거를 수 있게 역할 이름과 같다.
    assert [d.value for d in Department] == ["재무", "영업지원팀", "내부감사"]
    assert [s.value for s in TaskStatus] == ["열림", "진행", "완료"]
    assert [s.value for s in PaymentStatus] == ["회신대기", "성공", "계좌오류"]
    # 은행 회신 결과에는 회신대기가 없다.
    assert [r.value for r in BankResult] == ["성공", "계좌오류"]
    assert {a.value for a in IdentityAttrType} == {
        "대표자",
        "주소",
        "등록계좌",
        "실입금계좌",
    }
