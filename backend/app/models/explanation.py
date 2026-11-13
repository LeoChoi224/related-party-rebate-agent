"""소명 요청 · 회신 · 주장 대조.

ExplanationRequest: 영업지원팀 · 영업임원이 대리점에 보낸 소명 요청. 건은 소명대기가 된다.
ExplanationReply: 대리점 회신 [모의]. 요청 하나에 회신 하나이고, 보완 회신은 새 요청으로 받는다.
    AI 판단(explanation_review 가 저장)과 영업지원팀 확인 결과를 한 행에 남긴다.
    AI 판단은 17 의 ai_recommendation 과 의미가 달라(증빙 충분 · 부족) 따로 둔다.
    대체 모드(키 없음 · 2회 실패)면 AI 판단 컬럼이 비고 fallback_used 가 참이다.
ExplanationCheck: 회신 속 주장 하나를 데이터와 대조한 결과(일치 · 불일치 · 확인불가)와 조회한 근거 행.
"""

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExplanationRequest(Base):
    __tablename__ = "explanation_request"

    exp_id: Mapped[int] = mapped_column(primary_key=True)
    rebate_id: Mapped[str] = mapped_column(ForeignKey("rebate_claim.rebate_id"))
    # list[str] 는 SQLAlchemy 가 컬럼 타입을 스스로 정하지 못해 JSON 을 직접 적는다.
    requested_items: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str]
    requested_by: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ExplanationReply(Base):
    __tablename__ = "explanation_reply"

    reply_id: Mapped[int] = mapped_column(primary_key=True)
    # 요청 하나에 회신 하나. 서비스 검사(409)를 거치지 않는 경로도 DB 가 막는다.
    exp_id: Mapped[int] = mapped_column(
        ForeignKey("explanation_request.exp_id"), unique=True
    )
    raw_text: Mapped[str]
    provenance: Mapped[str]
    # AI 판단. 검토 전이거나 대체 모드면 비어 있다.
    ai_judgement: Mapped[str | None]
    ai_rationale: Mapped[list[str]] = mapped_column(JSON, default=list)
    missing_evidence: Mapped[list[str]] = mapped_column(JSON, default=list)
    follow_up_request: Mapped[str | None]
    ai_confidence: Mapped[float | None]
    verified: Mapped[bool] = mapped_column(default=False)
    fallback_used: Mapped[bool] = mapped_column(default=False)
    model: Mapped[str | None]
    # 영업지원팀 확인. 확인 전에는 비어 있다. AI 판단이 없으면 비교할 것이 없어 agreed 도 비어 있다.
    review_result: Mapped[str | None]
    review_reason: Mapped[str | None]
    reviewed_by: Mapped[str | None]
    reviewed_at: Mapped[datetime | None]
    agreed: Mapped[bool | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ExplanationCheck(Base):
    __tablename__ = "explanation_check"

    check_id: Mapped[int] = mapped_column(primary_key=True)
    reply_id: Mapped[int] = mapped_column(ForeignKey("explanation_reply.reply_id"))
    # 회신에서 뽑은 순서(1부터)
    seq: Mapped[int]
    claim_text: Mapped[str]
    verdict: Mapped[str]
    finding: Mapped[str]
    # 이 주장에 부른 도구 이름과, 그 결과에 실제로 나온 근거 행("파일:행")
    tool_used: Mapped[list[str]] = mapped_column(JSON)
    evidence_ref: Mapped[list[str]] = mapped_column(JSON)
