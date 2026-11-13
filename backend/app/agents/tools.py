"""그래프가 쓰는 조회 도구: 대리점 속성, 입금 기록, 계좌 사용 대리점, 관련자 그룹, 미수채권. 읽기 전용이다.

- 순수 조회 함수 `(session, 인자) -> dict` 와, 그것을 LangChain 도구로 감싸는 `build_tools(session)` 두 층이다.
- 결과의 모든 근거는 "근거_행": "파일:행" 으로 달려 있다. 노드가 `collect_refs` 로 모아
  AI 가 인용한 근거가 실제 조회 결과에 있는지 가드가 대조한다.
- 잘못된 입력(없는 대리점 등)은 예외가 아니라 {"error": ...} 로 돌려준다. 모델이 읽고 다시 조회할 수 있어야 한다.
- 어떤 대리점이든 조회할 수 있다. 계좌 소유를 대조하려면 다른 대리점의 등록계좌를 봐야 하고, 전부 읽기만 한다.
"""

from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Agency,
    ARItem,
    Deposit,
    GroupMember,
    GroupVersion,
    IdentityAttribute,
    RelatedGroup,
    RelationEdge,
)
from app.models.enums import IdentityAttrType

REF_KEY = "근거_행"
ACCOUNT_TYPES = (IdentityAttrType.REGISTERED_ACCOUNT, IdentityAttrType.DEPOSIT_ACCOUNT)


def _no_agency(session: Session, agency_id: str) -> dict[str, Any] | None:
    if session.get(Agency, agency_id.strip()) is None:
        return {"error": f"대리점 {agency_id} 이(가) 없습니다", "rows": []}
    return None


def lookup_agency_attributes(session: Session, agency_id: str) -> dict[str, Any]:
    """대리점의 지금 유효한 대표자 · 주소 · 등록계좌 · 실입금계좌."""
    agency_id = agency_id.strip()
    if (error := _no_agency(session, agency_id)) is not None:
        return error
    attrs = session.scalars(
        select(IdentityAttribute)
        .where(
            IdentityAttribute.agency_id == agency_id,
            IdentityAttribute.valid_to.is_(None),
        )
        .order_by(IdentityAttribute.id)
    ).all()
    return {
        "rows": [
            {
                "대리점": agency_id,
                "속성": a.attr_type,
                "값": a.value,
                REF_KEY: a.source_ref,
            }
            for a in attrs
        ]
    }


def list_deposits(session: Session, agency_id: str) -> dict[str, Any]:
    """대리점의 입금 기록. 돈이 실제로 들어온 계좌(실입금계좌)가 들어 있다."""
    agency_id = agency_id.strip()
    if (error := _no_agency(session, agency_id)) is not None:
        return error
    deposits = session.scalars(
        select(Deposit)
        .where(Deposit.agency_id == agency_id)
        .order_by(Deposit.deposit_date, Deposit.deposit_id)
    ).all()
    return {
        "rows": [
            {
                "입금_ID": d.deposit_id,
                "대리점": agency_id,
                "입금일": d.deposit_date.isoformat(),
                "금액_krw": d.amount_krw,
                "실입금계좌": d.bank_account_no,
                REF_KEY: f"{d.source_file}:{d.source_row}",
            }
            for d in deposits
        ]
    }


def find_agencies_by_account(session: Session, account: str) -> dict[str, Any]:
    """계좌 문자열(예: 국민 412-27-556310)을 등록계좌 또는 실입금계좌로 가진 대리점들. 정확한 문자열 비교."""
    account = account.strip()
    attrs = session.scalars(
        select(IdentityAttribute)
        .where(
            IdentityAttribute.value == account,
            IdentityAttribute.attr_type.in_(ACCOUNT_TYPES),
            IdentityAttribute.valid_to.is_(None),
        )
        .order_by(IdentityAttribute.agency_id, IdentityAttribute.id)
    ).all()
    return {
        "rows": [
            {
                "대리점": a.agency_id,
                "속성": a.attr_type,
                "값": a.value,
                REF_KEY: a.source_ref,
            }
            for a in attrs
        ]
    }


def get_related_group(session: Session, agency_id: str) -> dict[str, Any]:
    """지금 버전에서 대리점이 속한 관련자 그룹과, 대리점이 낀 일치 쌍(정황 포함)의 일치 속성."""
    agency_id = agency_id.strip()
    if (error := _no_agency(session, agency_id)) is not None:
        return error
    version_id = session.scalar(
        select(GroupVersion.group_version_id).where(GroupVersion.is_current)
    )
    group = session.scalar(
        select(RelatedGroup)
        .join(GroupMember, GroupMember.group_id == RelatedGroup.group_id)
        .where(
            RelatedGroup.group_version_id == version_id,
            GroupMember.agency_id == agency_id,
        )
    )
    members = (
        session.scalars(
            select(GroupMember.agency_id)
            .where(GroupMember.group_id == group.group_id)
            .order_by(GroupMember.agency_id)
        ).all()
        if group is not None
        else []
    )
    edges = session.scalars(
        select(RelationEdge)
        .where(
            RelationEdge.group_version_id == version_id,
            (RelationEdge.agency_a == agency_id) | (RelationEdge.agency_b == agency_id),
        )
        .order_by(RelationEdge.edge_id)
    ).all()
    return {
        "그룹": group.label if group is not None else None,
        "구성_대리점": list(members),
        "rows": [
            {
                "대리점_쌍": [e.agency_a, e.agency_b],
                "판정": e.judgement,
                "일치_속성": [
                    {
                        "속성": m["attr"],
                        "값": m["value"],
                        REF_KEY: list(m["refs_a"]) + list(m["refs_b"]),
                    }
                    for m in e.matched_attrs
                ],
            }
            for e in edges
        ],
    }


def list_receivables(session: Session, agency_id: str) -> dict[str, Any]:
    """대리점의 미수채권. 잔액과 연체일수."""
    agency_id = agency_id.strip()
    if (error := _no_agency(session, agency_id)) is not None:
        return error
    items = session.scalars(
        select(ARItem).where(ARItem.agency_id == agency_id).order_by(ARItem.ar_id)
    ).all()
    return {
        "rows": [
            {
                "채권_ID": i.ar_id,
                "대리점": agency_id,
                "만기일": i.due_date.isoformat(),
                "금액_krw": i.amount_krw,
                "잔액_krw": i.outstanding_krw,
                "연체일수": i.aging_days,
                REF_KEY: f"{i.source_file}:{i.source_row}",
            }
            for i in items
        ]
    }


def collect_refs(result: Any) -> set[str]:
    """도구 결과 안의 모든 근거 행("파일:행"). 중첩된 dict · list 도 훑는다."""
    refs: set[str] = set()
    if isinstance(result, dict):
        for key, value in result.items():
            if key == REF_KEY:
                refs.update([value] if isinstance(value, str) else list(value))
            else:
                refs |= collect_refs(value)
    elif isinstance(result, list):
        for item in result:
            refs |= collect_refs(item)
    return refs


def build_tools(session: Session) -> list[BaseTool]:
    """세션을 클로저로 잡은 LangChain 도구들. 세션은 요청마다 달라 상태에 저장하지 않는다."""

    def attributes_tool(agency_id: str) -> dict[str, Any]:
        return lookup_agency_attributes(session, agency_id)

    def deposits_tool(agency_id: str) -> dict[str, Any]:
        return list_deposits(session, agency_id)

    def account_tool(account: str) -> dict[str, Any]:
        return find_agencies_by_account(session, account)

    def group_tool(agency_id: str) -> dict[str, Any]:
        return get_related_group(session, agency_id)

    def receivables_tool(agency_id: str) -> dict[str, Any]:
        return list_receivables(session, agency_id)

    return [
        StructuredTool.from_function(
            attributes_tool,
            name="lookup_agency_attributes",
            description=lookup_agency_attributes.__doc__,
        ),
        StructuredTool.from_function(
            deposits_tool,
            name="list_deposits",
            description=list_deposits.__doc__,
        ),
        StructuredTool.from_function(
            account_tool,
            name="find_agencies_by_account",
            description=find_agencies_by_account.__doc__,
        ),
        StructuredTool.from_function(
            group_tool,
            name="get_related_group",
            description=get_related_group.__doc__,
        ),
        StructuredTool.from_function(
            receivables_tool,
            name="list_receivables",
            description=list_receivables.__doc__,
        ),
    ]
