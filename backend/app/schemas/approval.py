"""결정 요청 · 결과.

결정자 이름 · 역할은 시연용으로 본문에 담는다(실제 시스템이면 로그인 토큰에서 꺼낸다).
역할은 문자열로 받는다. 결재권자가 아닌 역할(재무 등)은 형식 오류(422)가 아니라
권한 부족(403)이어야 하기 때문이다. AI 추천과 다르면 사유 필수는 25 에서 더한다.
"""

from pydantic import BaseModel, Field, model_validator

from app.models.enums import Decision


class DecisionRequest(BaseModel):
    decision: Decision
    reason: str = ""
    actor: str = Field(min_length=1, examples=["박임원"])
    role: str = Field(min_length=1, examples=["영업임원"])

    @model_validator(mode="after")
    def reject_needs_reason(self) -> "DecisionRequest":
        # decision 과 reason 을 함께 봐야 해서 필드가 아니라 객체 전체를 검사한다.
        if self.decision == Decision.REJECT and not self.reason.strip():
            raise ValueError("반려 사유를 입력해야 합니다")
        return self


class ApprovalDecisionResult(BaseModel):
    request_id: int
    decision: str
    decided_by: str
    rebate_ids: list[str]


class ClaimDecisionResult(BaseModel):
    rebate_id: str
    status: str
