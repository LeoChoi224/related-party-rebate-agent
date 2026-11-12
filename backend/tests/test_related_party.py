"""관련자 판정 엔진 테스트.

앞부분은 가짜 식별속성 몇 줄로 규칙의 경계(1개 · 2개 일치, 계좌 묶음, 전이 연결)를 보고,
가운데는 원본 데이터로 로드맵 완료 기준(G1, D-024–D-011 3개 일치, D-034–D-041 정황)을,
끝은 버전 저장(시더가 만든 버전 1, 다시 계산하면 버전 2)을 본다.
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    GroupMember,
    GroupVersion,
    IdentityAttribute,
    RelatedGroup,
    RelationEdge,
)
from app.models.enums import IdentityAttrType, Provenance, RelationJudgement
from app.seed.csv_loader import AGENCY_CSV, DEPOSIT_CSV
from app.services.related_party import find_related_parties, save_group_version

REP = IdentityAttrType.REPRESENTATIVE
ADDR = IdentityAttrType.ADDRESS
REG = IdentityAttrType.REGISTERED_ACCOUNT
DEP = IdentityAttrType.DEPOSIT_ACCOUNT
RELATED = RelationJudgement.RELATED
CIRCUMSTANTIAL = RelationJudgement.CIRCUMSTANTIAL
G1 = ("D-011", "D-024", "D-037")


def attr(agency_id, attr_type, value, ref="test.csv:1", valid_to=None):
    """DB 에 넣지 않은 식별속성 한 줄. 계산 함수는 DB 를 몰라도 된다."""
    return IdentityAttribute(
        agency_id=agency_id,
        attr_type=attr_type,
        value=value,
        provenance=Provenance.ORIGINAL,
        source_ref=ref,
        valid_from=date(2024, 1, 1),
        valid_to=valid_to,
    )


def summary(result):
    return [
        (m.agency_a, m.agency_b, m.match_count, m.judgement) for m in result.matches
    ]


def source_attrs(engine):
    with Session(engine) as session:
        return session.scalars(select(IdentityAttribute)).all()


def test_two_matches_are_related_and_one_is_circumstantial():
    """2개 일치는 관련자로 묶이고, 1개 일치는 정황으로만 남는다."""
    result = find_related_parties(
        [
            attr("D-001", REP, "김철수"),
            attr("D-001", ADDR, "서울시 1"),
            attr("D-002", REP, "김철수"),
            attr("D-002", ADDR, "서울시 1"),
            attr("D-003", REP, "김철수"),
        ]
    )
    assert summary(result) == [
        ("D-001", "D-002", 2, RELATED),
        ("D-001", "D-003", 1, CIRCUMSTANTIAL),
        ("D-002", "D-003", 1, CIRCUMSTANTIAL),
    ]
    assert result.groups == [("D-001", "D-002")]


def test_related_pairs_are_connected_transitively():
    """A-B, B-C 가 관련자면 A-C 가 정황뿐이어도 셋이 한 그룹이다."""
    result = find_related_parties(
        [
            attr("D-001", REP, "김철수"),
            attr("D-001", ADDR, "서울시 1"),
            attr("D-002", REP, "김철수"),
            attr("D-002", ADDR, "서울시 1"),
            attr("D-002", REG, "국민 1"),
            attr("D-003", REP, "김철수"),
            attr("D-003", REG, "국민 1"),
        ]
    )
    assert ("D-001", "D-003", 1, CIRCUMSTANTIAL) in summary(result)
    assert result.groups == [("D-001", "D-002", "D-003")]


def test_deposit_account_matches_registered_account():
    """한쪽의 실입금계좌가 다른 쪽의 등록계좌와 같아도 계좌 일치다."""
    result = find_related_parties(
        [
            attr("D-001", REP, "김철수"),
            attr("D-001", REG, "국민 1", ref="agency.csv:2"),
            attr("D-002", REP, "김철수"),
            attr("D-002", REG, "하나 9"),
            attr("D-002", DEP, "국민 1", ref="deposit.csv:5"),
        ]
    )
    (match,) = result.matches
    assert match.judgement == RELATED
    assert match.matched_attrs[1] == {
        "attr": "계좌",
        "value": "국민 1",
        "refs_a": ["agency.csv:2"],
        "refs_b": ["deposit.csv:5"],
    }


def test_two_shared_accounts_still_count_as_one_attr():
    """계좌 두 개를 함께 써도 계좌는 속성 1개라 정황이다. 근거는 둘 다 남긴다."""
    result = find_related_parties(
        [
            attr("D-001", REG, "국민 1"),
            attr("D-001", DEP, "하나 9"),
            attr("D-002", REG, "하나 9"),
            attr("D-002", DEP, "국민 1"),
        ]
    )
    (match,) = result.matches
    assert [item["value"] for item in match.matched_attrs] == ["국민 1", "하나 9"]
    assert match.match_count == 1
    assert match.judgement == CIRCUMSTANTIAL
    assert result.groups == []


def test_closed_attribute_is_ignored():
    """정정으로 유효기간이 닫힌 속성은 비교하지 않는다."""
    result = find_related_parties(
        [
            attr("D-001", REP, "김철수"),
            attr("D-001", ADDR, "서울시 1", valid_to=date(2026, 7, 1)),
            attr("D-002", REP, "김철수"),
            attr("D-002", ADDR, "서울시 1"),
        ]
    )
    assert summary(result) == [("D-001", "D-002", 1, CIRCUMSTANTIAL)]
    assert result.groups == []


def test_empty_input_gives_empty_result():
    """식별속성이 없으면 예외 없이 빈 결과다."""
    result = find_related_parties([])
    assert result.matches == []
    assert result.groups == []


def test_groups_are_ordered_by_first_member():
    """그룹 안은 ID 순, 그룹끼리는 첫 구성원 순이라 다시 계산해도 G1·G2 가 같다."""
    rows = []
    for agency_id, name in [
        ("D-009", "B"),
        ("D-002", "A"),
        ("D-007", "B"),
        ("D-005", "A"),
    ]:
        rows += [attr(agency_id, REP, name), attr(agency_id, ADDR, f"{name} 주소")]
    rows.append(attr("D-001", REP, "혼자"))
    assert find_related_parties(rows).groups == [("D-002", "D-005"), ("D-007", "D-009")]


def test_source_data_gives_g1_and_four_pairs(seeded_engine):
    """원본: 일치 쌍 4개(관련자 3, 정황 1), 그룹은 G1 하나."""
    result = find_related_parties(source_attrs(seeded_engine))
    assert summary(result) == [
        ("D-011", "D-024", 3, RELATED),
        ("D-011", "D-037", 2, RELATED),
        ("D-024", "D-037", 2, RELATED),
        ("D-034", "D-041", 1, CIRCUMSTANTIAL),
    ]
    assert result.groups == [G1]


def test_d024_account_evidence_cites_deposit_rows(seeded_engine):
    """D-011–D-024 계좌 근거는 D-011 마스터 12행과 D-024 입금 14 · 15행이다."""
    match = find_related_parties(source_attrs(seeded_engine)).matches[0]
    account = match.matched_attrs[2]
    assert account["attr"] == "계좌"
    assert account["value"] == "국민 412-27-556310"
    assert f"{AGENCY_CSV}:12" in account["refs_a"]
    assert account["refs_b"] == [f"{DEPOSIT_CSV}:14", f"{DEPOSIT_CSV}:15"]


def test_g1_still_forms_without_deposit_accounts(seeded_engine):
    """실입금계좌를 빼면 D-024–D-037 은 정황이 되지만, G1 은 D-011 을 거쳐 그대로 묶인다."""
    attrs = [a for a in source_attrs(seeded_engine) if a.attr_type != DEP]
    result = find_related_parties(attrs)
    assert ("D-024", "D-037", 1, CIRCUMSTANTIAL) in summary(result)
    assert result.groups == [G1]


def test_seeded_db_has_g1_in_current_version_1(seeded_engine):
    """앱을 켜면 버전 1 에 G1 과 일치 관계 4개가 근거와 함께 저장돼 있다."""
    with Session(seeded_engine) as session:
        version = session.scalars(select(GroupVersion)).one()
        assert (version.version_no, version.is_current) == (1, True)
        group = session.scalars(select(RelatedGroup)).one()
        assert group.label == "G1"
        members = session.scalars(
            select(GroupMember.agency_id).order_by(GroupMember.agency_id)
        ).all()
        assert tuple(members) == G1
        edge = session.scalars(
            select(RelationEdge).where(
                RelationEdge.agency_a == "D-011", RelationEdge.agency_b == "D-024"
            )
        ).one()
        assert (edge.match_count, edge.judgement) == (3, "관련자")
        assert edge.matched_attrs[2]["refs_b"] == [
            f"{DEPOSIT_CSV}:14",
            f"{DEPOSIT_CSV}:15",
        ]


def test_saving_again_makes_new_current_version(seeded_engine):
    """다시 계산해 저장하면 버전 2 가 현재가 되고, 버전 1 과 그 그룹은 그대로 남는다."""
    with Session(seeded_engine) as session, session.begin():
        result = find_related_parties(session.scalars(select(IdentityAttribute)))
        assert save_group_version(session, result).version_no == 2

    with Session(seeded_engine) as session:
        versions = session.execute(
            select(GroupVersion.version_no, GroupVersion.is_current).order_by(
                GroupVersion.version_no
            )
        ).all()
        assert versions == [(1, False), (2, True)]
        labels = session.scalars(select(RelatedGroup.label)).all()
        assert labels == ["G1", "G1"]


def test_save_does_not_commit_by_itself(seeded_engine):
    """저장 함수는 commit 하지 않는다. 트랜잭션 없이 부르고 닫으면 남지 않는다."""
    with Session(seeded_engine) as session:
        save_group_version(session, find_related_parties([]))

    with Session(seeded_engine) as session:
        count = session.scalar(select(func.count()).select_from(GroupVersion))
        assert count == 1
