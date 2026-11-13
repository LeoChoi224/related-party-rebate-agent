"""AI 추천 기록(25): 세 AI 의 출력과 사람 결정, 일치율을 한 목록으로 모은다. 읽기만 한다.

- 장려금 검토(claim_review): ai_recommendation 행. 추천 vs 결정(승인 · 반려, "소명 먼저"는 반려 + 소명 요청).
- 소명 검토(explanation_review): AI 검토가 돈 소명 회신. AI 판단 vs 영업지원팀 확인(증빙 충분 · 부족).
- 상계 추천(22): AI 추천을 받은 상계 제안. 추천 상계액 vs 재무 결정(상계하지 않음 = 0원).
일치율의 분모는 AI 출력이 있고 사람이 결정한 것(compared)이다. 대체 모드는 비교할 것이 없어 빠진다.
"""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AIRecommendation,
    ApprovalItem,
    ExplanationReply,
    ExplanationRequest,
    OffsetProposal,
)
from app.schemas.ai_recommendation import AiKindStats, AiLogOut, AiLogRow
from app.services.claim_detail import TARGET_REQUEST

KIND_CLAIM = "장려금 검토"
KIND_EXPLANATION = "소명 검토"
KIND_OFFSET = "상계 추천"
KINDS = (KIND_CLAIM, KIND_EXPLANATION, KIND_OFFSET)


def _claim_rows(session: Session) -> list[AiLogRow]:
    first_item = {
        str(request_id): rebate_id
        for request_id, rebate_id in session.execute(
            select(ApprovalItem.request_id, func.min(ApprovalItem.rebate_id)).group_by(
                ApprovalItem.request_id
            )
        )
    }
    rows = []
    for rec in session.scalars(
        select(AIRecommendation).order_by(AIRecommendation.rec_id)
    ):
        rebate_id = (
            first_item.get(rec.target_id)
            if rec.target_type == TARGET_REQUEST
            else rec.target_id
        )
        rows.append(
            AiLogRow(
                kind=KIND_CLAIM,
                target=f"{rec.target_type}:{rec.target_id}",
                rebate_id=rebate_id,
                ai_output=rec.recommendation,
                human_decision=rec.human_decision,
                human_reason=rec.human_reason,
                agreed=rec.agreed,
                fallback_used=rec.fallback_used,
                authority_raised=rec.authority_raised,
                model=rec.model,
                created_at=rec.created_at,
            )
        )
    return rows


def _explanation_rows(session: Session) -> list[AiLogRow]:
    replies = session.execute(
        select(ExplanationReply, ExplanationRequest.rebate_id)
        .join(ExplanationRequest, ExplanationRequest.exp_id == ExplanationReply.exp_id)
        # AI 검토가 돈 회신만(검토 전 회신은 기록할 AI 출력이 없다).
        .where(or_(ExplanationReply.verified, ExplanationReply.fallback_used))
        .order_by(ExplanationReply.reply_id)
    ).all()
    return [
        AiLogRow(
            kind=KIND_EXPLANATION,
            target=f"explanation_reply:{reply.reply_id}",
            rebate_id=rebate_id,
            ai_output=reply.ai_judgement,
            human_decision=reply.review_result,
            human_reason=reply.review_reason,
            agreed=reply.agreed,
            fallback_used=reply.fallback_used,
            authority_raised=False,
            model=reply.model,
            created_at=reply.created_at,
        )
        for reply, rebate_id in replies
    ]


def _won(amount: int | None) -> str | None:
    return None if amount is None else f"{amount:,}원"


def _offset_rows(session: Session) -> list[AiLogRow]:
    proposals = session.scalars(
        select(OffsetProposal)
        .where(or_(OffsetProposal.verified, OffsetProposal.fallback_used))
        .order_by(OffsetProposal.offset_id)
    ).all()
    rows = []
    for p in proposals:
        # 재무가 상계하지 않기로 했으면 0원으로 적어 AI 의 0원 추천과 나란히 보이게 한다.
        if p.finance_decision is None:
            human = None
        elif p.offset_amount_krw is None:
            human = "0원(상계 안 함)"
        else:
            human = _won(p.offset_amount_krw)
        rows.append(
            AiLogRow(
                kind=KIND_OFFSET,
                target=f"offset_proposal:{p.offset_id}",
                rebate_id=p.rebate_id,
                ai_output=_won(p.ai_amount_krw),
                human_decision=human,
                human_reason=p.finance_reason,
                agreed=p.agreed,
                fallback_used=p.fallback_used,
                authority_raised=False,
                model=p.model,
                created_at=p.created_at,
            )
        )
    return rows


def _stats(kind: str, rows: list[AiLogRow]) -> AiKindStats:
    mine = [r for r in rows if r.kind == kind]
    compared = [r for r in mine if r.agreed is not None]
    agreed = sum(1 for r in compared if r.agreed)
    return AiKindStats(
        kind=kind,
        total=len(mine),
        fallback=sum(1 for r in mine if r.fallback_used),
        decided=sum(1 for r in mine if r.human_decision is not None),
        compared=len(compared),
        agreed=agreed,
        agreement_rate=agreed / len(compared) if compared else None,
        authority_raised=sum(1 for r in mine if r.authority_raised),
    )


def ai_log(session: Session) -> AiLogOut:
    """세 AI 의 기록(최신순)과 종류별 · 전체 집계."""
    rows = _claim_rows(session) + _explanation_rows(session) + _offset_rows(session)
    stats = [_stats(kind, rows) for kind in KINDS]
    total = AiKindStats(
        kind="전체",
        total=sum(s.total for s in stats),
        fallback=sum(s.fallback for s in stats),
        decided=sum(s.decided for s in stats),
        compared=sum(s.compared for s in stats),
        agreed=sum(s.agreed for s in stats),
        agreement_rate=None,
        authority_raised=sum(s.authority_raised for s in stats),
    )
    if total.compared:
        total.agreement_rate = total.agreed / total.compared
    # 시각은 초 단위라 겹친다. 같은 초면 종류 · 대상 순서를 지키려고 안정 정렬을 쓴다.
    rows.sort(key=lambda r: r.created_at, reverse=True)
    return AiLogOut(stats=[*stats, total], rows=rows)
