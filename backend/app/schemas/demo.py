"""시연 패널 요청 · 응답(26).

초기화 결과와 시나리오 이벤트 일괄 처리 결과. 정정 신고 · G1 결정 · 소명 회신은 업무 API 를 그대로 쓴다.
"""

from pydantic import BaseModel, Field

from app.models.enums import BankResult


class ResetResult(BaseModel):
    """표 이름별로 다시 채운 행 수."""

    counts: dict[str, int]


class StandaloneBatchRequest(BaseModel):
    period_ym: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-06"])


class StandaloneBatchResult(BaseModel):
    """단독 전결대기 건 일괄 전결 승인 · 지급 지시 결과. total_krw 는 지시한 금액 합계."""

    period_ym: str
    approved: int
    payment_ids: list[int]
    total_krw: int


class BankRepliesRequest(BaseModel):
    result: BankResult


class BankRepliesResult(BaseModel):
    """회신대기 지급 지시 전부에 넣은 은행 회신 [모의] 결과. by_claim_status 는 회신 뒤 건 상태별 건수."""

    result: str
    replied: int
    total_krw: int
    by_claim_status: dict[str, int]
