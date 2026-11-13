"""상계 제안(필수 확장) [가정].

OffsetProposal: 관련자 그룹 건이 승인됐을 때 같은 그룹의 연체 채권(90일 초과)과 상계하자는 제안.
건 하나에 제안 하나(지급 지시 · 대리점 동의가 건 단위라서). 정정 신고로 취소되면 다시 승인될 때 새 제안이 생긴다.
max_offset_krw 는 코드가 계산한 상계 한도이고, AI 추천 · 재무 결정은 이 값을 넘을 수 없다.
영업 의견 [주장](23) · AI 추천 [주장] · 재무 결정 · 대리점 동의 [모의] 를 한 행에 남긴다.
영업 의견은 대리점 관계 부담을 보고 고른 대안(전액 상계 · 부분 상계 · 지급 후 회수 약정)이고,
AI 추천의 사실과 재무 결정 화면에 들어간다. 결정은 재무가 하며 영업 의견을 따랐는지(sales_followed)를 남긴다.
AI 추천은 ai_recommendation(승인 · 반려 · 소명 먼저)과 뜻이 달라 소명 회신(18)처럼 이 행에 직접 둔다.
"""

from datetime import date, datetime

from sqlalchemy import JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OffsetProposal(Base):
    __tablename__ = "offset_proposal"

    offset_id: Mapped[int] = mapped_column(primary_key=True)
    rebate_id: Mapped[str] = mapped_column(ForeignKey("rebate_claim.rebate_id"))
    # 판정 당시 그룹. 이 그룹 구성원의 연체 채권이 상계 대상이다.
    group_id: Mapped[int] = mapped_column(ForeignKey("related_group.group_id"))
    # 제안 당시 그룹 연체 잔액과 코드가 계산한 상계 한도
    overdue_total_krw: Mapped[int]
    max_offset_krw: Mapped[int]
    status: Mapped[str]
    # 영업 의견 [주장](23). 입력 전이면 비어 있다. 부분 상계면 영업이 권한 상계액이 있다.
    sales_alternative: Mapped[str | None]
    sales_amount_krw: Mapped[int | None]
    sales_opinion: Mapped[str | None]
    sales_by: Mapped[str | None]
    sales_at: Mapped[datetime | None]
    # AI 추천 [주장]. 추천 전이거나 대체 모드면 비어 있다.
    ai_amount_krw: Mapped[int | None]
    ai_rationale: Mapped[list[str]] = mapped_column(JSON, default=list)
    ai_counter_evidence: Mapped[list[str]] = mapped_column(JSON, default=list)
    ai_confidence: Mapped[float | None]
    verified: Mapped[bool] = mapped_column(default=False)
    fallback_used: Mapped[bool] = mapped_column(default=False)
    model: Mapped[str | None]
    # 재무 결정. 결정 전에는 비어 있다. AI 추천이 없으면 비교할 것이 없어 agreed 도 비어 있다.
    finance_decision: Mapped[str | None]
    offset_amount_krw: Mapped[int | None]
    finance_reason: Mapped[str | None]
    decided_by: Mapped[str | None]
    decided_at: Mapped[datetime | None]
    agreed: Mapped[bool | None]
    # 영업 의견이 있으면 재무 결정이 그 대안과 같은지. 의견이 없으면 비어 있다.
    sales_followed: Mapped[bool | None]
    # 지급 후 회수 약정(23): 상계하지 않고 지급하되 이 날까지 연체 채권을 회수하기로 함
    collection_due_date: Mapped[date | None]
    # 대리점 동의 [모의]
    agency_consent: Mapped[str | None]
    consent_provenance: Mapped[str | None]
    consented_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
