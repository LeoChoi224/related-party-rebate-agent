"""관련자 근거(일치 쌍과 원본 행) 응답. 그룹 상세 · 버전 이력은 범위 밖이다."""

from pydantic import BaseModel, ConfigDict


class MatchedAttr(BaseModel):
    """일치한 속성 하나. refs_a · refs_b 는 양쪽 근거 행("파일:행")이다.

    지금은 모두 원본 행이다. 정정 신고(20)로 다른 출처 값이 들어오면 출처를 더한다.
    """

    attr: str
    value: str
    refs_a: list[str]
    refs_b: list[str]


class RelationEdgeOut(BaseModel):
    """1개 이상 일치한 두 대리점. agency_a 가 작은 ID 다."""

    model_config = ConfigDict(from_attributes=True)

    agency_a: str
    agency_b: str
    judgement: str
    match_count: int
    matched_attrs: list[MatchedAttr]
