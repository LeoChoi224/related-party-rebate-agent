"""소명 요청 · 회신 · 확인.

요청: 반려 · 지급보류 건에서 영업지원팀 · 영업임원이 만들고, 건은 소명대기가 된다(10 규칙표가 소명 요청 작업을 만든다).
    상신대기 건은 요청하지 못한다. 전이표는 허용하지만 G1 건 하나만 빠지면 3건이 한 묶음인 승인 요청과 어긋난다.
    상신 건은 임원이 승인 요청을 반려한 뒤(건이 반려가 됨) 이 길로 온다. 반려 결정과의 연결은 21 이다.
회신: 대리점 회신 [모의]. 요청 하나에 회신 하나이고 건 상태는 바뀌지 않는다.
확인: 영업지원팀만. 증빙 충분 → 관계확인 → 바로 재판정해 전결대기 · 상신대기(재상신), 증빙 부족 → 지급보류. 확인 결과 컬럼은 AI 검토를 거쳤는지와
    상관없이 이 서비스가 적는다(그래프를 한 번도 안 돌린 회신도 확인할 수 있어야 한다).
모두 commit 하지 않는다. 409 는 InvalidTransitionError, 403 은 InsufficientAuthorityError 를 쓴다.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    ExplanationCheck,
    ExplanationReply,
    ExplanationRequest,
    RebateClaim,
)
from app.models.enums import (
    ApproverRole,
    ClaimStatus,
    ExplanationJudgement,
    ExplanationStatus,
    Provenance,
)
from app.schemas.explanation import (
    ExplanationCheckOut,
    ExplanationOut,
    ExplanationReplyOut,
)
from app.services.approval import InsufficientAuthorityError
from app.services.claim_state import InvalidTransitionError, transition
from app.services.rejudge import rejudge_claims

REQUESTABLE = frozenset({ClaimStatus.REJECTED, ClaimStatus.ON_HOLD})
REQUESTER_ROLES = frozenset({ApproverRole.SALES_SUPPORT, ApproverRole.SALES_EXECUTIVE})
OPEN_STATUSES = (ExplanationStatus.AWAITING_REPLY, ExplanationStatus.REPLIED)
CONFIRMED_TO_STATUS = {
    ExplanationJudgement.SUFFICIENT: ClaimStatus.RELATION_CHECKED,
    ExplanationJudgement.INSUFFICIENT: ClaimStatus.ON_HOLD,
}


def request_explanation(
    session: Session,
    rebate_id: str,
    *,
    items: list[str],
    actor: str,
    role: str,
) -> ExplanationRequest:
    """반려 · 지급보류 건에 소명을 요청하고 건을 소명대기로 보낸다."""
    claim = session.get(RebateClaim, rebate_id)
    if claim is None:
        raise LookupError(f"장려금 건 {rebate_id} 이(가) 없습니다")
    if role not in REQUESTER_ROLES:
        raise InsufficientAuthorityError(
            f"{role} 은(는) 소명을 요청할 수 없습니다 ({rebate_id})"
        )
    if claim.status not in REQUESTABLE:
        raise InvalidTransitionError(
            f"소명 요청은 반려 · 지급보류 건만 할 수 있습니다: {claim.status} ({rebate_id})"
        )
    open_request = session.scalar(
        select(ExplanationRequest).where(
            ExplanationRequest.rebate_id == rebate_id,
            ExplanationRequest.status.in_(OPEN_STATUSES),
        )
    )
    if open_request is not None:
        raise InvalidTransitionError(
            f"이미 진행 중인 소명 요청이 있습니다: #{open_request.exp_id} ({rebate_id})"
        )

    cleaned = [item.strip() for item in items]
    request = ExplanationRequest(
        rebate_id=rebate_id,
        requested_items=cleaned,
        status=ExplanationStatus.AWAITING_REPLY,
        requested_by=actor,
    )
    session.add(request)
    session.flush()
    transition(
        session,
        claim,
        ClaimStatus.AWAITING_EXPLANATION,
        actor=actor,
        actor_role=role,
        reason=f"소명 요청: {', '.join(cleaned)}",
        payload={"exp_id": request.exp_id},
    )
    return request


def request_explanations(
    session: Session,
    claims: list[RebateClaim],
    items: list[str],
    *,
    actor: str,
    role: str,
) -> list[int]:
    """반려된 건마다 같은 항목으로 소명을 요청한다(21). 대리점마다 회신이 따로 오므로 요청은 건 단위다."""
    if not items:
        return []
    return [
        request_explanation(
            session, claim.rebate_id, items=items, actor=actor, role=role
        ).exp_id
        for claim in claims
    ]


def register_reply(session: Session, exp_id: int, raw_text: str) -> ExplanationReply:
    """대리점 회신 [모의] 을 등록한다. 요청 하나에 한 번만."""
    request = session.get(ExplanationRequest, exp_id)
    if request is None:
        raise LookupError(f"소명 요청 {exp_id} 이(가) 없습니다")
    if request.status != ExplanationStatus.AWAITING_REPLY:
        raise InvalidTransitionError(
            f"회신대기 요청만 회신을 받을 수 있습니다: {request.status} (요청 {exp_id})"
        )
    claim = session.get(RebateClaim, request.rebate_id)
    if claim.status != ClaimStatus.AWAITING_EXPLANATION:
        raise InvalidTransitionError(
            f"소명대기 건만 회신을 받을 수 있습니다: {claim.status} ({claim.rebate_id})"
        )
    reply = ExplanationReply(
        exp_id=exp_id, raw_text=raw_text.strip(), provenance=Provenance.MOCK
    )
    session.add(reply)
    request.status = ExplanationStatus.REPLIED
    session.flush()
    return reply


def confirm_explanation(
    session: Session,
    reply_id: int,
    *,
    judgement: ExplanationJudgement,
    reason: str,
    actor: str,
    role: str,
) -> tuple[ExplanationReply, RebateClaim]:
    """영업지원팀이 소명을 확인한다. 증빙 충분 → 관계확인, 증빙 부족 → 지급보류."""
    reply = session.get(ExplanationReply, reply_id)
    if reply is None:
        raise LookupError(f"소명 회신 {reply_id} 이(가) 없습니다")
    if role != ApproverRole.SALES_SUPPORT:
        raise InsufficientAuthorityError(
            f"{role} 은(는) 소명을 확인할 수 없습니다 (회신 {reply_id})"
        )
    request = session.get(ExplanationRequest, reply.exp_id)
    if request.status != ExplanationStatus.REPLIED:
        raise InvalidTransitionError(
            f"확인 전 회신만 확인할 수 있습니다: {request.status} (회신 {reply_id})"
        )
    claim = session.get(RebateClaim, request.rebate_id)
    # 전이표가 소명대기가 아닌 건을 막는다(409). 확인 결과는 전이가 통과한 뒤에 적는다.
    transition(
        session,
        claim,
        CONFIRMED_TO_STATUS[judgement],
        actor=actor,
        actor_role=role,
        reason=reason.strip() or f"소명 확인: {judgement}",
        payload={"exp_id": request.exp_id, "reply_id": reply_id},
    )
    if judgement == ExplanationJudgement.SUFFICIENT:
        # 소명이 충분하면 건을 지금 그룹으로 다시 판정해 결재 경로에 다시 올린다(재상신, 21).
        rejudge_claims(
            session,
            [claim],
            actor=actor,
            role=role,
            reason="소명 증빙 충분 — 재판정",
        )
    reply.review_result = judgement
    reply.review_reason = reason.strip() or None
    reply.reviewed_by = actor
    reply.reviewed_at = func.now()
    reply.agreed = (
        None if reply.ai_judgement is None else reply.ai_judgement == judgement
    )
    request.status = ExplanationStatus.CONFIRMED
    session.flush()
    return reply, claim


def explanation_out(session: Session, request: ExplanationRequest) -> ExplanationOut:
    """요청 하나를 회신 · 주장 대조 결과까지 묶은 응답으로 만든다. 읽기만 한다."""
    out = ExplanationOut.model_validate(request)
    reply = session.scalar(
        select(ExplanationReply).where(ExplanationReply.exp_id == request.exp_id)
    )
    if reply is not None:
        checks = session.scalars(
            select(ExplanationCheck)
            .where(ExplanationCheck.reply_id == reply.reply_id)
            .order_by(ExplanationCheck.seq)
        ).all()
        out.reply = ExplanationReplyOut.model_validate(reply).model_copy(
            update={"checks": [ExplanationCheckOut.model_validate(c) for c in checks]}
        )
    return out


def list_explanations(session: Session, rebate_id: str) -> list[ExplanationOut]:
    """건의 소명 요청들(요청 ID 순 — 시각은 초 단위라 겹침)."""
    requests = session.scalars(
        select(ExplanationRequest)
        .where(ExplanationRequest.rebate_id == rebate_id)
        .order_by(ExplanationRequest.exp_id)
    ).all()
    return [explanation_out(session, r) for r in requests]
