"""감사 사후 검토(24) 요청과 결과.

역할은 문자열로 받는다. 내부감사가 아닌 역할은 형식 오류(422)가 아니라 권한 부족(403)이다.
"""

from datetime import date

from pydantic import BaseModel, Field


class RetroReviewRequest(BaseModel):
    actor: str = Field(min_length=1, examples=["최감사"])
    role: str = Field(min_length=1, examples=["내부감사"])


class RetroFinding(BaseModel):
    """결재 단계가 모자랐던 지급 건 하나. task_id 는 이번 실행에서 새로 연 작업(이미 있으면 비어 있음)."""

    rebate_id: str
    agency_id: str
    period_ym: str
    group_label: str | None
    group_sum_krw: int
    min_authority: str
    original_approver: str
    rebate_amount_krw: int
    original_payment_date: date | None
    task_id: int | None


class RetroReviewResult(BaseModel):
    """checked = 다시 판정한 원본 지급 건 수, total_krw = 위반 건 지급액 합계."""

    checked: int
    periods: list[str]
    findings: list[RetroFinding]
    total_krw: int
    created_tasks: int
