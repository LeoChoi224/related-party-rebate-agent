"""상계(필수 확장) 스키마 [가정].

OffsetAdvice: AI 상계액 추천의 구조화 출력. 필드 설명이 그대로 LLM 지시가 된다.
OffsetOut: 건 상세의 상계 칸. 그룹의 연체 채권(지금 잔액)과 이 제안이 만든 잔액 조정을 함께 싣는다.
결정자 이름 · 역할은 다른 결정처럼 본문에서 받는다(09). 재무가 아닌 역할은 422 가 아니라 403 이다.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import AgencyConsent, Decision, SalesAlternative
from app.schemas.common import UtcDatetime


class OffsetAdvice(BaseModel):
    # 범위 제약(ge · le)은 넣지 않는다(ClaimAssessment 와 같은 이유). 범위는 가드가 검사한다.
    offset_amount_krw: int = Field(
        description="권하는 상계액(원). 0 이면 상계하지 말고 전액 지급하라는 뜻. 상계 한도를 넘을 수 없다"
    )
    rationale: list[str] = Field(
        description="추천 근거 문장들. 채권 사실은 끝에 근거 행(파일:행)을 붙인다"
    )
    counter_evidence: list[str] = Field(
        description="상계에 반대하거나 확인이 더 필요한 점. 없으면 빈 목록"
    )
    confidence: float = Field(description="추천에 대한 확신도. 0 에서 1 사이")


class ARItemOut(BaseModel):
    """상계 대상 연체 채권 한 줄. remaining_krw = 원본 잔액 - 상계 조정 합계."""

    ar_id: str
    agency_id: str
    due_date: date
    aging_days: int
    outstanding_krw: int
    remaining_krw: int
    source_file: str
    source_row: int


class ARAdjustmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ar_id: str
    amount_krw: int
    provenance: str
    applied_at: UtcDatetime


class OffsetOut(BaseModel):
    """상계 제안 하나. 서버가 저장한 값을 그대로 보여 주고 화면은 다시 계산하지 않는다."""

    offset_id: int
    rebate_id: str
    group_label: str
    overdue_total_krw: int
    max_offset_krw: int
    status: str
    sales_alternative: str | None
    sales_amount_krw: int | None
    sales_opinion: str | None
    sales_by: str | None
    sales_at: UtcDatetime | None
    ai_amount_krw: int | None
    ai_rationale: list[str]
    ai_counter_evidence: list[str]
    ai_confidence: float | None
    verified: bool
    fallback_used: bool
    model: str | None
    finance_decision: str | None
    offset_amount_krw: int | None
    finance_reason: str | None
    decided_by: str | None
    decided_at: UtcDatetime | None
    agreed: bool | None
    sales_followed: bool | None
    collection_due_date: date | None
    agency_consent: str | None
    consent_provenance: str | None
    consented_at: UtcDatetime | None
    created_at: UtcDatetime
    # 그룹의 90일 초과 연체 채권(상계 순서: 이 건의 대리점 먼저, 오래된 것 먼저)
    overdue_items: list[ARItemOut]
    adjustments: list[ARAdjustmentOut]


class SalesOpinionRequest(BaseModel):
    """영업 의견(23). 부분 상계면 권하는 상계액이 필요하고, 다른 대안이면 비워 둔다."""

    alternative: SalesAlternative
    amount_krw: int | None = None
    opinion: str = Field(
        min_length=1,
        examples=["D-011 은 6월 신규 판촉 중이라 전액 상계 시 관계 부담 큼"],
    )
    actor: str = Field(min_length=1, examples=["김지원"])
    role: str = Field(min_length=1, examples=["영업지원팀"])

    @model_validator(mode="after")
    def check_amount(self) -> "SalesOpinionRequest":
        if not self.opinion.strip():
            raise ValueError("영업 의견을 입력해야 합니다")
        partial = self.alternative == SalesAlternative.PARTIAL_OFFSET
        if partial and (self.amount_krw is None or self.amount_krw < 1):
            raise ValueError("부분 상계는 1원 이상의 상계액을 입력해야 합니다")
        if not partial and self.amount_krw is not None:
            raise ValueError("상계액은 부분 상계일 때만 입력합니다")
        return self


class OffsetDecisionRequest(BaseModel):
    """재무 결정. 승인이면 상계액이, 반려(상계하지 않음)면 사유가 필요하다.

    반려하면서 회수 약정 기한을 넣으면 "지급 후 회수 약정"이다(23).
    """

    decision: Decision
    offset_amount_krw: int | None = None
    reason: str = ""
    collection_due_date: date | None = None
    actor: str = Field(min_length=1, examples=["이재무"])
    role: str = Field(min_length=1, examples=["재무"])

    @model_validator(mode="after")
    def check_amount_and_reason(self) -> "OffsetDecisionRequest":
        if self.decision == Decision.APPROVE:
            if self.offset_amount_krw is None or self.offset_amount_krw < 1:
                raise ValueError(
                    "상계를 승인하려면 1원 이상의 상계액을 입력해야 합니다"
                )
            if self.collection_due_date is not None:
                raise ValueError("회수 약정 기한은 상계하지 않을 때만 넣습니다")
        elif not self.reason.strip():
            raise ValueError("상계하지 않는 사유를 입력해야 합니다")
        return self


class AgencyConsentRequest(BaseModel):
    consent: AgencyConsent


class OffsetResult(BaseModel):
    """재무 결정 · 대리점 동의 뒤의 제안과 건. payable_krw 는 지금 지급할 남은 금액이다."""

    offset: OffsetOut
    claim_status: str
    payable_krw: int
