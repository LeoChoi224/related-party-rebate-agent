"""장려금 건 API 응답.

접수 결과와 처리함 목록 한 줄. 건 상세 응답은 14 에서 더한다.
"""

from pydantic import BaseModel


class IntakeResult(BaseModel):
    """대상월 접수 요약. 건별 목록은 처리함 API(13)가 맡는다."""

    period_ym: str
    received: int
    by_status: dict[str, int]


class ClaimListItem(BaseModel):
    """처리함 목록 한 줄. 건 · 대리점 이름 · 그룹 라벨을 라우트가 모아 만든다.

    min_authority · group_sum_krw 는 한도 판정 전이면, group_label 은 단독 대리점이면 비어 있다.
    """

    rebate_id: str
    agency_id: str
    agency_name: str
    period_ym: str
    rebate_amount_krw: int
    status: str
    min_authority: str | None
    group_label: str | None
    group_sum_krw: int | None
