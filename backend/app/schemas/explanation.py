"""소명 스키마.

ExtractedClaims · CheckResult · ExplanationAssessment: explanation_review 그래프가 LLM 에게 받는 구조화 출력.
    필드 설명이 그대로 LLM 지시가 된다.
ExplanationRequestCreate · ReplyCreate · ExplanationConfirmRequest: API 요청.
ExplanationOut: 건 상세와 소명 API 가 돌려주는 요청 + 회신 + 주장 대조 결과.
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import CheckVerdict, ExplanationJudgement
from app.schemas.common import UtcDatetime


class ExtractedClaims(BaseModel):
    claims: list[str] = Field(
        description=(
            "회신에서 데이터(입금 기록, 대리점 정보, 관련자 그룹, 미수채권)로 확인할 수 있는 "
            "사실 주장. 원문에 가깝게 한 문장씩. 사과 · 의견 · 약속은 뺀다"
        )
    )


class CheckResult(BaseModel):
    verdict: CheckVerdict = Field(
        description=(
            "일치: 조회 결과가 주장을 뒷받침. 불일치: 조회 결과가 주장과 모순. "
            "확인불가: 데이터로 판단할 수 없음"
        )
    )
    finding: str = Field(description="무엇을 조회해 무엇을 확인했는지 한 문장")
    evidence_refs: list[str] = Field(
        description="판정 근거 행(파일:행). 도구 조회 결과에 나온 것만 쓰고 지어내지 않는다"
    )


class ExplanationAssessment(BaseModel):
    # 범위 제약(ge · le)은 넣지 않는다. OpenAI 구조화 출력은 JSON 스키마 제약을 일부만 받아
    # 호출이 실패할 수 있다. confidence 범위는 가드(agents/guards.py)가 검사한다.
    judgement: ExplanationJudgement = Field(
        description="모든 주장이 데이터와 일치할 때만 '증빙 충분'. 하나라도 아니면 '증빙 부족'"
    )
    rationale: list[str] = Field(
        description="판단의 근거 문장들. 데이터에서 온 사실은 끝에 근거 행(파일:행)을 붙인다"
    )
    missing_evidence: list[str] = Field(
        description="더 받아야 할 증빙. 충분하면 빈 목록"
    )
    follow_up_request: str = Field(
        description="증빙 부족이면 대리점에 보낼 추가 요청문. 충분하면 빈 문자열"
    )
    confidence: float = Field(description="판단에 대한 확신도. 0 에서 1 사이")


class ExplanationRequestCreate(BaseModel):
    requested_items: list[str] = Field(min_length=1, examples=[["계좌 공유 사유"]])
    actor: str = Field(min_length=1, examples=["김지원"])
    role: str = Field(min_length=1, examples=["영업지원팀"])

    @model_validator(mode="after")
    def items_not_blank(self) -> "ExplanationRequestCreate":
        if any(not item.strip() for item in self.requested_items):
            raise ValueError("요청 항목은 비울 수 없습니다")
        return self


class ReplyCreate(BaseModel):
    raw_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def text_not_blank(self) -> "ReplyCreate":
        if not self.raw_text.strip():
            raise ValueError("회신 내용을 입력해야 합니다")
        return self


class ExplanationConfirmRequest(BaseModel):
    judgement: ExplanationJudgement
    reason: str = ""
    actor: str = Field(min_length=1, examples=["김지원"])
    role: str = Field(min_length=1, examples=["영업지원팀"])

    @model_validator(mode="after")
    def insufficient_needs_reason(self) -> "ExplanationConfirmRequest":
        if (
            self.judgement == ExplanationJudgement.INSUFFICIENT
            and not self.reason.strip()
        ):
            raise ValueError("증빙 부족 사유를 입력해야 합니다")
        return self


class ExplanationCheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    check_id: int
    seq: int
    claim_text: str
    verdict: str
    finding: str
    tool_used: list[str]
    evidence_ref: list[str]


class ExplanationReplyOut(BaseModel):
    """회신과 AI 판단 [주장], 사람 확인. 화면은 저장된 값을 그대로 보여 주고 다시 판단하지 않는다."""

    model_config = ConfigDict(from_attributes=True)

    reply_id: int
    raw_text: str
    provenance: str
    ai_judgement: str | None
    ai_rationale: list[str]
    missing_evidence: list[str]
    follow_up_request: str | None
    ai_confidence: float | None
    verified: bool
    fallback_used: bool
    model: str | None
    review_result: str | None
    review_reason: str | None
    reviewed_by: str | None
    reviewed_at: UtcDatetime | None
    agreed: bool | None
    created_at: UtcDatetime
    checks: list[ExplanationCheckOut] = []


class ExplanationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    exp_id: int
    rebate_id: str
    requested_items: list[str]
    status: str
    requested_by: str
    created_at: UtcDatetime
    reply: ExplanationReplyOut | None = None


class ExplanationConfirmResult(BaseModel):
    reply_id: int
    judgement: str
    claim_status: str
