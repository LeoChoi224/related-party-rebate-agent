"""AI 추천과 사람 결정의 일치 · 사유 필수(25).

사람이 AI 추천과 다르게 결정하면 사유를 남겨야 한다. 다르게 결정하는 것 자체는 막지 않는다(최종 결정은 사람).
대체 모드(AI 판단 없음)면 비교할 것이 없어 사유를 요구하지 않는다.
세 AI 가 쓰는 일치 규칙을 한 곳에 둔다: 장려금 검토(claim_review) · 소명 검토(18) · 상계 추천(22).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIRecommendation
from app.models.enums import Decision, Recommendation


class ReasonRequiredError(ValueError):
    """AI 추천과 다른 결정인데 사유가 없다. API 는 422 로 돌려준다."""


def recommendation_matches(
    recommendation: str, decision: str, *, explained: bool
) -> bool:
    """장려금 검토 추천과 사람 결정이 같은가. "소명 먼저"는 반려하면서 소명을 요청한 것(21)과 같다."""
    if recommendation == Recommendation.EXPLAIN_FIRST:
        return decision == Decision.REJECT and explained
    return recommendation == decision


def require_reason(
    agreed: bool | None, reason: str, *, ai_output: str, human: str
) -> None:
    """다르게 결정했는데(agreed 가 거짓) 사유가 비었으면 막는다. 비교할 AI 판단이 없으면(None) 통과."""
    if agreed is False and not reason.strip():
        raise ReasonRequiredError(
            f"AI 추천({ai_output})과 다른 결정({human})은 사유를 입력해야 합니다"
        )


def pending_recommendation(
    session: Session, target_type: str, target_id: str
) -> AIRecommendation | None:
    """검토 단위의 결정 전 AI 추천(가장 최근). 대체 모드여도 행은 있지만 추천은 비어 있다."""
    return session.scalar(
        select(AIRecommendation)
        .where(
            AIRecommendation.target_type == target_type,
            AIRecommendation.target_id == target_id,
            AIRecommendation.human_decision.is_(None),
        )
        .order_by(AIRecommendation.rec_id.desc())
        .limit(1)
    )


def check_claim_decision(
    session: Session,
    target_type: str,
    target_id: str,
    *,
    decision: Decision,
    reason: str,
    explained: bool,
) -> None:
    """전결 · 승인 요청 결정이 기다리는 AI 추천과 다르면 사유를 요구한다."""
    rec = pending_recommendation(session, target_type, target_id)
    if rec is None or rec.recommendation is None:
        return
    human = f"{decision} + 소명 요청" if explained else str(decision)
    require_reason(
        recommendation_matches(rec.recommendation, decision, explained=explained),
        reason,
        ai_output=rec.recommendation,
        human=human,
    )
