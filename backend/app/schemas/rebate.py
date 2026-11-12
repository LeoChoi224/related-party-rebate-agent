"""장려금 건 API 응답.

지금은 접수 결과만 둔다. 처리함 목록 · 건 상세 응답은 13 · 14 에서 더한다.
"""

from pydantic import BaseModel


class IntakeResult(BaseModel):
    """대상월 접수 요약. 건별 목록은 처리함 API(13)가 맡는다."""

    period_ym: str
    received: int
    by_status: dict[str, int]
