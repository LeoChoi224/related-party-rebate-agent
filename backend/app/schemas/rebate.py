"""장려금 건 API 응답: 접수 결과, 처리함 목록 한 줄, 건 상세."""

from datetime import date

from pydantic import BaseModel

from app.schemas.ai_recommendation import AiReviewOut
from app.schemas.approval import ApprovalSummary
from app.schemas.event_log import EventLogOut
from app.schemas.explanation import ExplanationOut
from app.schemas.payment import PaymentOut
from app.schemas.related_party import RelationEdgeOut


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


class ClaimUnitMember(BaseModel):
    """판정 단위(그룹 또는 단독 대리점)의 같은 달 건 하나."""

    rebate_id: str
    agency_id: str
    agency_name: str
    rebate_amount_krw: int
    status: str


class ClaimDetail(BaseModel):
    """건 상세. 원본 기록, 코드 판정, 판정 근거, 승인 요청, 지급, 이력을 한 번에 담는다.

    limit_krw 는 규정 한도다. 화면이 2,000,000 을 따로 적지 않게 서버 상수를 그대로 싣는다.
    """

    # 원본 기록 [원본]
    rebate_id: str
    agency_id: str
    agency_name: str
    period_ym: str
    sales_performance_krw: int
    rebate_amount_krw: int
    original_status: str
    original_approver: str | None
    original_payment_date: date | None
    source_file: str
    source_row: int
    # 업무 상태와 코드 판정. 판정 전이면 min_authority · group_sum_krw 가 비어 있다.
    status: str
    min_authority: str | None
    group_label: str | None
    group_sum_krw: int | None
    limit_krw: int
    # 판정 근거와 그 뒤의 처리
    unit_claims: list[ClaimUnitMember]
    evidence: list[RelationEdgeOut]
    approval: ApprovalSummary | None
    payments: list[PaymentOut]
    events: list[EventLogOut]
    # 이 건의 검토 단위(상신 건이면 승인 요청)에서 가장 최근 AI 추천 [주장]. 검토 전이면 없음.
    ai_review: AiReviewOut | None
    # 이 건의 소명 요청들(요청 ID 순). 요청마다 회신 · AI 주장 대조 · 사람 확인이 붙는다.
    explanations: list[ExplanationOut]
