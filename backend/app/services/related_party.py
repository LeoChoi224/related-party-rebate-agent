"""관련자 판정 엔진.

대표자·주소·계좌 중 2개 이상 같으면 관련자, 1개만 같으면 정황으로 본다.
계좌는 등록계좌와 실입금계좌를 한 묶음으로 보고 속성 1개로 센다.
관련자 쌍은 전이적으로 묶고, 2곳 이상 묶인 것만 그룹으로 남긴다.

계산(find_related_parties)은 DB 를 모르는 순수 함수라, 정정 신고로 다시 계산할 때(20)도
그대로 쓴다. 저장은 save_group_version 이 새 GroupVersion 으로 한다.
"""

import itertools
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import (
    GroupMember,
    GroupVersion,
    IdentityAttribute,
    RelatedGroup,
    RelationEdge,
)
from app.models.enums import IdentityAttrType, MatchAttr, RelationJudgement

# "동일 관련자(대표자·주소·정산계좌 2개 이상 일치)" — approval_authority_policy.md
RELATED_MIN_MATCHES = 2

# 저장은 출처별 4종, 판정은 규정대로 3종. 계좌를 1개로 세는 결정은 이 표 한 곳에만 있다.
ATTR_TO_MATCH = {
    IdentityAttrType.REPRESENTATIVE: MatchAttr.REPRESENTATIVE,
    IdentityAttrType.ADDRESS: MatchAttr.ADDRESS,
    IdentityAttrType.REGISTERED_ACCOUNT: MatchAttr.ACCOUNT,
    IdentityAttrType.DEPOSIT_ACCOUNT: MatchAttr.ACCOUNT,
}


@dataclass(frozen=True)
class RelationMatch:
    """1개 이상 일치한 두 대리점. matched_attrs 는 RelationEdge 에 그대로 저장한다."""

    agency_a: str
    agency_b: str
    matched_attrs: list[dict]

    @property
    def match_count(self) -> int:
        # 같은 속성에서 값 두 개가 겹쳐도(공유 계좌 2개) 속성은 하나로 센다.
        return len({item["attr"] for item in self.matched_attrs})

    @property
    def judgement(self) -> RelationJudgement:
        if self.match_count >= RELATED_MIN_MATCHES:
            return RelationJudgement.RELATED
        return RelationJudgement.CIRCUMSTANTIAL


@dataclass(frozen=True)
class GroupingResult:
    matches: list[RelationMatch]
    # 2곳 이상 묶인 그룹만. 그룹 안은 ID 순, 그룹끼리는 첫 구성원 순이다.
    groups: list[tuple[str, ...]]


def find_related_parties(attrs: Iterable[IdentityAttribute]) -> GroupingResult:
    """식별속성으로 대리점 쌍을 판정하고 관련자를 그룹으로 묶는다."""
    # 대리점 → 판정 속성 → 값 → 근거 행 목록
    values: dict[str, dict[MatchAttr, dict[str, list[str]]]] = {}
    for attr in attrs:
        # 정정으로 닫힌 속성은 지금의 관계가 아니다.
        if attr.valid_to is not None:
            continue
        by_attr = values.setdefault(attr.agency_id, {})
        by_value = by_attr.setdefault(ATTR_TO_MATCH[attr.attr_type], {})
        by_value.setdefault(attr.value, []).append(attr.source_ref)

    matches = []
    # 정렬한 ID 로 짝을 지으면 agency_a 가 늘 작은 ID 다.
    for a, b in itertools.combinations(sorted(values), 2):
        evidence = []
        for match_attr in MatchAttr:
            refs_a = values[a].get(match_attr, {})
            refs_b = values[b].get(match_attr, {})
            for value in sorted(refs_a.keys() & refs_b.keys()):
                evidence.append(
                    {
                        "attr": match_attr,
                        "value": value,
                        # 복사해 둔다. 같은 목록을 여러 쌍이 나눠 쓰면 한쪽 수정이 번진다.
                        "refs_a": list(refs_a[value]),
                        "refs_b": list(refs_b[value]),
                    }
                )
        if evidence:
            matches.append(RelationMatch(a, b, evidence))

    related_pairs = [
        (m.agency_a, m.agency_b)
        for m in matches
        if m.judgement == RelationJudgement.RELATED
    ]
    return GroupingResult(matches=matches, groups=_connect(related_pairs))


def _connect(pairs: Iterable[tuple[str, str]]) -> list[tuple[str, ...]]:
    """관련자 쌍을 전이적으로 묶는다(유니온-파인드). A-B, B-C 면 A·B·C 가 한 그룹."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            # 한 칸씩 건너뛰며 올라가 다음 find 가 짧아지게 한다(경로 압축).
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pairs:
        parent[find(b)] = find(a)

    members: dict[str, list[str]] = {}
    for x in parent:
        members.setdefault(find(x), []).append(x)
    return sorted(tuple(sorted(group)) for group in members.values() if len(group) >= 2)


def save_group_version(session: Session, result: GroupingResult) -> GroupVersion:
    """계산 결과를 새 버전으로 저장하고, 이전 버전은 현재가 아니게 한다.

    commit 하지 않는다. 부르는 쪽 트랜잭션 안에서 다른 변경과 함께 확정 · 취소된다.
    """
    session.execute(
        update(GroupVersion).where(GroupVersion.is_current).values(is_current=False)
    )
    last_no = session.scalar(select(func.max(GroupVersion.version_no))) or 0
    version = GroupVersion(version_no=last_no + 1, is_current=True)
    session.add(version)
    # 아래 행들이 가리킬 group_version_id 를 받으려면 먼저 DB 에 넣어야 한다.
    session.flush()

    for i, members in enumerate(result.groups, start=1):
        group = RelatedGroup(group_version_id=version.group_version_id, label=f"G{i}")
        session.add(group)
        session.flush()
        session.add_all(
            GroupMember(group_id=group.group_id, agency_id=agency_id)
            for agency_id in members
        )

    session.add_all(
        RelationEdge(
            group_version_id=version.group_version_id,
            agency_a=match.agency_a,
            agency_b=match.agency_b,
            matched_attrs=match.matched_attrs,
            match_count=match.match_count,
            judgement=match.judgement,
        )
        for match in result.matches
    )
    session.flush()
    return version
