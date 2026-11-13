"""AI 추천과 사람 결정.

AIRecommendation: 그래프가 낸 추천 1건과 사람의 최종 결정을 한 행에 남긴다.
검토 단위(전결 건 하나 또는 승인 요청 하나)마다 검토할 때마다 한 행이다.
ai_authority 는 AI 가 낸 값 그대로 두고, 코드 값(min_authority)보다 낮았으면 authority_raised 를 남긴다.
대체 모드(키 없음 · 2회 실패)면 추천 · 근거가 비어 있고 fallback_used 가 참이다.
"""

from datetime import datetime

from sqlalchemy import JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AIRecommendation(Base):
    __tablename__ = "ai_recommendation"

    rec_id: Mapped[int] = mapped_column(primary_key=True)
    graph: Mapped[str]
    thread_id: Mapped[str]
    # 대상이 건 또는 승인 요청이라 외래키 대신 "종류 + ID" 로 가리킨다(Task 와 같음).
    target_type: Mapped[str]
    target_id: Mapped[str]
    # AI 출력. 대체 모드면 비어 있다.
    recommendation: Mapped[str | None]
    # list[str] 는 SQLAlchemy 가 컬럼 타입을 스스로 정하지 못해 JSON 을 직접 적는다.
    rationale: Mapped[list[str]] = mapped_column(JSON)
    counter_evidence: Mapped[list[str]] = mapped_column(JSON)
    confidence: Mapped[float | None]
    # 코드 판정과 가드 결과
    min_authority: Mapped[str]
    ai_authority: Mapped[str | None]
    authority_raised: Mapped[bool]
    verified: Mapped[bool]
    fallback_used: Mapped[bool]
    model: Mapped[str | None]
    # 사람 결정. 결정 전에는 비어 있다. 대체 모드면 비교할 추천이 없어 agreed 도 비어 있다.
    human_decision: Mapped[str | None]
    human_reason: Mapped[str | None]
    agreed: Mapped[bool | None]
    decided_by: Mapped[str | None]
    decided_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
