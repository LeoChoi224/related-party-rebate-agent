"""소명 조회 도구 테스트: 원본 데이터로 G1 공유계좌 사실을 도구가 근거 행과 함께 찾는지."""

import pytest
from sqlalchemy.orm import Session

from app.agents.tools import (
    build_tools,
    collect_refs,
    find_agencies_by_account,
    get_related_group,
    list_deposits,
    list_receivables,
    lookup_agency_attributes,
)

G1_ACCOUNT = "국민 412-27-556310"


@pytest.fixture
def session(seeded_engine):
    with Session(seeded_engine) as s:
        yield s


def test_deposits_of_d024_use_the_g1_shared_account(session):
    """D-024 입금 2건(DP-00013 · 14)은 등록계좌가 아니라 G1 공유계좌로 들어왔다."""
    rows = list_deposits(session, "D-024")["rows"]
    assert [r["입금_ID"] for r in rows] == ["DP-00013", "DP-00014"]
    assert {r["실입금계좌"] for r in rows} == {G1_ACCOUNT}
    assert all(":" in r["근거_행"] for r in rows)


def test_account_is_registered_to_d011_and_d037(session):
    """완료 기준의 핵심: 그 계좌는 세무대리인 계좌가 아니라 D-011 · D-037 의 등록계좌다."""
    rows = find_agencies_by_account(session, G1_ACCOUNT)["rows"]
    registered = {r["대리점"] for r in rows if r["속성"] == "등록계좌"}
    assert registered == {"D-011", "D-037"}
    assert {r["대리점"] for r in rows} == {"D-011", "D-024", "D-037"}


def test_unknown_account_is_empty_not_error(session):
    assert find_agencies_by_account(session, "없은 000-00-000000") == {"rows": []}


def test_attributes_list_only_valid_ones_with_source(session):
    rows = lookup_agency_attributes(session, "D-024")["rows"]
    assert {r["속성"] for r in rows} >= {"대표자", "주소", "등록계좌"}
    assert all(r["근거_행"] for r in rows)


def test_related_group_shows_g1_members_and_matches(session):
    result = get_related_group(session, "D-024")
    assert result["그룹"] == "G1"
    assert result["구성_대리점"] == ["D-011", "D-024", "D-037"]
    assert result["rows"]
    assert collect_refs(result)


def test_standalone_agency_has_no_group(session):
    """그룹이 없는 대리점: 그룹 없음, 쌍도 없다(정황 쌍이 있으면 쌍만 나온다)."""
    result = get_related_group(session, "D-001")
    assert result["그룹"] is None and result["구성_대리점"] == []


def test_receivables_of_g1_member_have_aging(session):
    rows = list_receivables(session, "D-011")["rows"]
    assert rows
    assert {"잔액_krw", "연체일수", "근거_행"} <= set(rows[0])


@pytest.mark.parametrize(
    "tool",
    [
        lookup_agency_attributes,
        list_deposits,
        get_related_group,
        list_receivables,
    ],
)
def test_unknown_agency_returns_error_not_exception(session, tool):
    """없는 대리점은 예외 대신 오류 문장을 돌려줘 모델이 다시 조회할 수 있다."""
    result = tool(session, "D-999")
    assert "D-999" in result["error"] and result["rows"] == []


def test_collect_refs_walks_nested_results():
    result = {
        "rows": [
            {"근거_행": "a.csv:1"},
            {"일치_속성": [{"근거_행": ["b.csv:2", "c.csv:3"]}]},
        ]
    }
    assert collect_refs(result) == {"a.csv:1", "b.csv:2", "c.csv:3"}


def test_build_tools_exposes_five_named_tools_that_run(session):
    tools = {t.name: t for t in build_tools(session)}
    assert set(tools) == {
        "lookup_agency_attributes",
        "list_deposits",
        "find_agencies_by_account",
        "get_related_group",
        "list_receivables",
    }
    result = tools["find_agencies_by_account"].invoke({"account": G1_ACCOUNT})
    assert {r["대리점"] for r in result["rows"]} == {"D-011", "D-024", "D-037"}
