"""관련자 표 4개 모델 테스트: 외래키, 구성원 중복 금지, JSON 근거 저장, 생성 시각, 코드 값."""

from datetime import date, datetime

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import make_engine
from app.models import (
    Agency,
    Base,
    GroupMember,
    GroupVersion,
    RelatedGroup,
    RelationEdge,
)
from app.models.enums import MatchAttr, RelationJudgement

EVIDENCE = [
    {
        "attr": "계좌",
        "value": "국민 412-27-556310",
        "refs_a": ["01_corevia/master/m_agency_cv.csv:12"],
        "refs_b": ["01_corevia/financials/fin_collection_history_cv.csv:14"],
    }
]


@pytest.fixture
def db_engine(tmp_path):
    """ERD 의 모든 표를 만든 임시 파일 DB."""
    eng = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def make_agency(agency_id: str) -> Agency:
    return Agency(
        agency_id=agency_id,
        agency_name="테스트대리점",
        representative_name="박상현",
        business_reg_no="123-45-67890",
        address="성남시 상공로 128",
        bank_account_no="국민 412-27-556310",
        rebate_eligible=True,
        registered_date=date(2024, 1, 2),
        source_file="m_agency_cv.csv",
        source_row=12,
    )


def add_version_and_group(session: Session) -> RelatedGroup:
    """대리점 2곳, 버전 1, 그룹 G1 을 넣고 그룹을 돌려준다."""
    session.add_all([make_agency("D-011"), make_agency("D-024")])
    version = GroupVersion(version_no=1, is_current=True)
    session.add(version)
    session.flush()
    group = RelatedGroup(group_version_id=version.group_version_id, label="G1")
    session.add(group)
    session.flush()
    return group


def test_foreign_keys_point_to_parent_tables(db_engine):
    """그룹은 버전을, 구성원은 그룹과 대리점을, 일치 관계는 버전과 대리점 둘을 가리킨다."""
    inspector = inspect(db_engine)

    def fk_map(table: str) -> dict[str, str]:
        return {
            fk["constrained_columns"][0]: fk["referred_table"]
            for fk in inspector.get_foreign_keys(table)
        }

    assert fk_map("related_group") == {"group_version_id": "group_version"}
    assert fk_map("group_member") == {
        "group_id": "related_group",
        "agency_id": "agency",
    }
    assert fk_map("relation_edge") == {
        "group_version_id": "group_version",
        "agency_a": "agency",
        "agency_b": "agency",
    }


def test_group_member_rejects_same_agency_twice(db_engine):
    """한 그룹에 같은 대리점을 두 번 넣으면 기본키 검사에 걸린다."""
    with Session(db_engine) as session, session.begin():
        group_id = add_version_and_group(session).group_id
        session.add(GroupMember(group_id=group_id, agency_id="D-011"))
    with (
        pytest.raises(IntegrityError),
        Session(db_engine) as session,
        session.begin(),
    ):
        session.add(GroupMember(group_id=group_id, agency_id="D-011"))


def test_member_of_unknown_agency_is_rejected(db_engine):
    """없는 대리점은 그룹 구성원이 될 수 없다."""
    with Session(db_engine) as session, session.begin():
        group_id = add_version_and_group(session).group_id
    with (
        pytest.raises(IntegrityError),
        Session(db_engine) as session,
        session.begin(),
    ):
        session.add(GroupMember(group_id=group_id, agency_id="D-999"))


def test_relation_edge_keeps_json_evidence(db_engine):
    """근거 목록은 JSON 으로 저장되고 같은 모양 · 한글 그대로 돌아온다."""
    with Session(db_engine) as session, session.begin():
        group = add_version_and_group(session)
        session.add(
            RelationEdge(
                group_version_id=group.group_version_id,
                agency_a="D-011",
                agency_b="D-024",
                matched_attrs=EVIDENCE,
                match_count=1,
                judgement=RelationJudgement.CIRCUMSTANTIAL,
            )
        )

    with Session(db_engine) as session:
        edge = session.scalars(select(RelationEdge)).one()
        assert edge.matched_attrs == EVIDENCE
        assert edge.judgement == "정황"

    # SQL 로 직접 보면 한글이 \uXXXX 로 이스케이프돼 있다. ORM 으로 읽을 때만 한글이다.
    with db_engine.connect() as conn:
        raw = conn.execute(text("SELECT matched_attrs FROM relation_edge")).scalar()
        assert "\\uacc4\\uc88c" in raw


def test_group_version_created_at_is_filled_by_db(db_engine):
    """생성 시각은 넣지 않아도 DB 가 채우고 datetime 으로 돌아온다."""
    with Session(db_engine) as session, session.begin():
        session.add(GroupVersion(version_no=1, is_current=True))

    with Session(db_engine) as session:
        version = session.scalars(select(GroupVersion)).one()
        assert isinstance(version.created_at, datetime)


def test_enum_values_match_rule_labels():
    """판정 속성은 규정의 3종(계좌는 하나), 판정 값은 관련자 · 정황이다."""
    assert [a.value for a in MatchAttr] == ["대표자", "주소", "계좌"]
    assert {j.value for j in RelationJudgement} == {"관련자", "정황"}
