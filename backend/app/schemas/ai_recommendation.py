"""AI 추천 스키마.

ClaimAssessment: claim_review 그래프가 LLM 에게 받는 구조화 출력. 필드 설명이 그대로 LLM 지시가 된다.
AiReviewOut: 건 상세의 AI 추천 패널 응답.
"""

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ApproverRole, Recommendation
from app.schemas.common import UtcDatetime


class ClaimAssessment(BaseModel):
    # 범위 제약(ge · le)은 넣지 않는다. OpenAI 구조화 출력은 JSON 스키마 제약을 일부만 받아
    # 호출이 실패할 수 있다. confidence 범위는 가드(agents/guards.py)가 검사한다.
    recommendation: Recommendation = Field(
        description="결재권자에게 권하는 결정. 증빙이 더 필요하면 '소명 먼저'"
    )
    ai_authority: ApproverRole = Field(
        description="이 건을 결정해야 할 결재권자. 판정 단위 합산이 한도를 넘으면 영업임원"
    )
    group_sum_krw: int = Field(
        description="판정 단위 합산 금액(원). 주어진 값을 그대로 옮기고 다시 계산하지 않는다"
    )
    rationale: list[str] = Field(
        description="추천의 근거 문장들. 데이터에서 온 사실은 끝에 근거 행(파일:행)을 붙인다"
    )
    counter_evidence: list[str] = Field(
        description="추천과 반대 방향의 근거나 확인이 더 필요한 점. 없으면 빈 목록"
    )
    confidence: float = Field(description="추천에 대한 확신도. 0 에서 1 사이")


class AiReviewOut(BaseModel):
    """AI 추천 패널. 서버가 저장한 값을 그대로 보여 주고 화면은 다시 판단하지 않는다."""

    model_config = ConfigDict(from_attributes=True)

    rec_id: int
    target_type: str
    target_id: str
    recommendation: str | None
    rationale: list[str]
    counter_evidence: list[str]
    confidence: float | None
    min_authority: str
    ai_authority: str | None
    authority_raised: bool
    verified: bool
    fallback_used: bool
    model: str | None
    human_decision: str | None
    human_reason: str | None
    agreed: bool | None
    decided_by: str | None
    decided_at: UtcDatetime | None
    created_at: UtcDatetime
