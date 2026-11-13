"""결정 요청 · 결과, 건 상세에 싣는 승인 요청 요약.

결정자 이름 · 역할은 시연용으로 본문에 담는다(실제 시스템이면 로그인 토큰에서 꺼낸다).
역할은 문자열로 받는다. 결재권자가 아닌 역할(재무 등)은 형식 오류(422)가 아니라
권한 부족(403)이어야 하기 때문이다. AI 추천과 다르면 사유 필수는 25 에서 더한다.
"""

from pydantic import BaseModel, Field, model_validator

from app.models.enums import Decision
from app.schemas.common import UtcDatetime


class DecisionRequest(BaseModel):
    decision: Decision
    reason: str = ""
    actor: str = Field(min_length=1, examples=["박임원"])
    role: str = Field(min_length=1, examples=["영업임원"])
    # 반려하면서 대리점에 소명을 요청할 항목(21). 반려된 건마다 소명 요청이 하나씩 생긴다.
    explanation_items: list[str] = []

    @model_validator(mode="after")
    def reject_needs_reason(self) -> "DecisionRequest":
        # decision 과 reason 을 함께 봐야 해서 필드가 아니라 객체 전체를 검사한다.
        if self.decision == Decision.REJECT and not self.reason.strip():
            raise ValueError("반려 사유를 입력해야 합니다")
        if self.explanation_items:
            if self.decision != Decision.REJECT:
                raise ValueError("소명 요청은 반려할 때만 함께 보낼 수 있습니다")
            if any(not item.strip() for item in self.explanation_items):
                raise ValueError("소명 요청 항목은 비울 수 없습니다")
        return self


class ApprovalDecisionResult(BaseModel):
    request_id: int
    decision: str
    decided_by: str
    rebate_ids: list[str]
    # 반려와 함께 만든 소명 요청(21). 건마다 하나.
    explanation_ids: list[int] = []


class ClaimDecisionResult(BaseModel):
    rebate_id: str
    status: str
    explanation_ids: list[int] = []


class ApprovalSummary(BaseModel):
    """건 상세의 승인 요청 칸. 결정 전에는 결정 · 사유 · 결정자 · 시각이 비어 있다.

    rebate_ids 는 이 요청을 결정하면 함께 바뀌는 건이다.
    """

    request_id: int
    approver_role: str
    group_sum_krw: int
    decision: str | None
    reason: str | None
    decided_by: str | None
    decided_at: UtcDatetime | None
    rebate_ids: list[str]
