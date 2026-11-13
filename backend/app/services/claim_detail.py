"""건 상세 조회.

여러 표에 흩어진 판정 근거(판정 단위 구성 건 · 관련자 일치 쌍), 승인 요청, 상계, 지급, 이력을
한 응답으로 모은다. 읽기만 하고 아무것도 바꾸지 않는다.
AI 검토 단위(review_unit)도 여기서 정한다. 상세가 그 단위의 추천을 싣고, 그래프(17)가 같은 함수를 쓴다.
결과 모양을 만드는 것 자체가 일이라, 다른 서비스와 달리 응답 스키마를 바로 돌려준다.
"""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    Agency,
    AIRecommendation,
    ApprovalItem,
    ApprovalRequest,
    BankReply,
    EventLog,
    GroupMember,
    GroupVersion,
    PaymentOrder,
    RebateClaim,
    RelatedGroup,
    RelationEdge,
)
from app.schemas.ai_recommendation import AiReviewOut
from app.schemas.approval import ApprovalSummary
from app.schemas.event_log import EventLogOut
from app.schemas.payment import PaymentOut
from app.schemas.rebate import ClaimDetail, ClaimUnitMember
from app.schemas.related_party import RelationEdgeOut
from app.services.approval_authority import REBATE_LIMIT_KRW
from app.services.explanation import list_explanations
from app.services.offset import list_offsets, payable_krw

# AI 검토 단위의 종류. EventLog · Task 의 대상 종류와 같은 표 이름 표기다.
TARGET_CLAIM = "rebate_claim"
TARGET_REQUEST = "approval_request"


def review_unit(session: Session, rebate_id: str) -> tuple[str, str]:
    """건의 AI 검토 단위. 승인 요청에 들어간 건(상신)이면 그 요청, 아니면 건 하나.

    G1 은 결정 한 번(승인 요청)으로 3건이 함께 바뀌므로 검토도 요청 하나로 한다.
    """
    # 21 에서 반려 뒤 재상신하면 요청이 하나 더 생긴다. 가장 최근 요청이 지금 단위다.
    request_id = session.scalar(
        select(ApprovalItem.request_id)
        .where(ApprovalItem.rebate_id == rebate_id)
        .order_by(ApprovalItem.request_id.desc())
        .limit(1)
    )
    if request_id is not None:
        return TARGET_REQUEST, str(request_id)
    return TARGET_CLAIM, rebate_id


def get_claim_detail(session: Session, rebate_id: str) -> ClaimDetail:
    """건 하나의 상세. 건이 없으면 LookupError(API 404)."""
    claim = session.get(RebateClaim, rebate_id)
    if claim is None:
        raise LookupError(f"장려금 건 {rebate_id} 이(가) 없습니다")
    agency_name = session.get(Agency, claim.agency_id).agency_name
    group = (
        session.get(RelatedGroup, claim.group_id)
        if claim.group_id is not None
        else None
    )

    return ClaimDetail(
        rebate_id=claim.rebate_id,
        agency_id=claim.agency_id,
        agency_name=agency_name,
        period_ym=claim.period_ym,
        sales_performance_krw=claim.sales_performance_krw,
        rebate_amount_krw=claim.rebate_amount_krw,
        original_status=claim.original_status,
        original_approver=claim.original_approver,
        original_payment_date=claim.original_payment_date,
        source_file=claim.source_file,
        source_row=claim.source_row,
        status=claim.status,
        min_authority=claim.min_authority,
        group_label=group.label if group is not None else None,
        group_sum_krw=claim.group_sum_krw,
        limit_krw=REBATE_LIMIT_KRW,
        unit_claims=_unit_claims(session, claim),
        evidence=_evidence(session, claim, group),
        approval=_approval(session, rebate_id),
        payments=_payments(session, rebate_id),
        events=_events(session, rebate_id),
        ai_review=_ai_review(session, rebate_id),
        explanations=list_explanations(session, rebate_id),
        offsets=list_offsets(session, rebate_id),
        payable_krw=payable_krw(session, claim),
    )


def _ai_review(session: Session, rebate_id: str) -> AiReviewOut | None:
    """건의 검토 단위에서 가장 최근 AI 추천. 시각은 초 단위로 겹쳐 rec_id 순으로 고른다."""
    target_type, target_id = review_unit(session, rebate_id)
    rec = session.scalar(
        select(AIRecommendation)
        .where(
            AIRecommendation.target_type == target_type,
            AIRecommendation.target_id == target_id,
        )
        .order_by(AIRecommendation.rec_id.desc())
        .limit(1)
    )
    return AiReviewOut.model_validate(rec) if rec is not None else None


def _unit_claims(session: Session, claim: RebateClaim) -> list[ClaimUnitMember]:
    """판정 단위의 같은 달 건. 판정 전이면 단위를 모르므로 비어 있다."""
    if claim.min_authority is None:
        return []
    query = (
        select(RebateClaim, Agency.agency_name)
        .join(Agency, RebateClaim.agency_id == Agency.agency_id)
        .order_by(RebateClaim.rebate_id)
    )
    if claim.group_id is not None:
        query = query.where(
            RebateClaim.group_id == claim.group_id,
            RebateClaim.period_ym == claim.period_ym,
        )
    else:
        query = query.where(RebateClaim.rebate_id == claim.rebate_id)
    return [
        ClaimUnitMember(
            rebate_id=c.rebate_id,
            agency_id=c.agency_id,
            agency_name=name,
            rebate_amount_krw=c.rebate_amount_krw,
            status=c.status,
        )
        for c, name in session.execute(query).all()
    ]


def _evidence(
    session: Session, claim: RebateClaim, group: RelatedGroup | None
) -> list[RelationEdgeOut]:
    """판정 단위 대리점이 낀 일치 쌍.

    그룹이 있으면 판정 당시 그룹의 버전에서 찾는다. 정정(20)으로 새 버전이 생겨도
    이 건이 왜 그 결재권자에게 갔는지는 당시 근거로 설명해야 하기 때문이다.
    그룹이 없으면(단독 · 판정 전) 지금 버전에서 이 대리점이 낀 쌍(정황 포함)을 찾는다.
    """
    if group is not None:
        version_id = group.group_version_id
        agencies = session.scalars(
            select(GroupMember.agency_id).where(GroupMember.group_id == group.group_id)
        ).all()
    else:
        version_id = session.scalar(
            select(GroupVersion.group_version_id).where(GroupVersion.is_current)
        )
        agencies = [claim.agency_id]
    edges = session.scalars(
        select(RelationEdge)
        .where(
            RelationEdge.group_version_id == version_id,
            or_(
                RelationEdge.agency_a.in_(agencies),
                RelationEdge.agency_b.in_(agencies),
            ),
        )
        .order_by(RelationEdge.edge_id)
    ).all()
    return [RelationEdgeOut.model_validate(edge) for edge in edges]


def _approval(session: Session, rebate_id: str) -> ApprovalSummary | None:
    """이 건이 든 마지막 승인 요청. 상신된 적이 없으면 None."""
    request = session.scalar(
        select(ApprovalRequest)
        .join(ApprovalItem, ApprovalItem.request_id == ApprovalRequest.request_id)
        .where(ApprovalItem.rebate_id == rebate_id)
        .order_by(ApprovalRequest.request_id.desc())
        .limit(1)
    )
    if request is None:
        return None
    rebate_ids = session.scalars(
        select(ApprovalItem.rebate_id)
        .where(ApprovalItem.request_id == request.request_id)
        .order_by(ApprovalItem.rebate_id)
    ).all()
    return ApprovalSummary(
        request_id=request.request_id,
        approver_role=request.approver_role,
        group_sum_krw=request.group_sum_krw,
        decision=request.decision,
        reason=request.reason,
        decided_by=request.decided_by,
        decided_at=request.decided_at,
        rebate_ids=list(rebate_ids),
    )


def _payments(session: Session, rebate_id: str) -> list[PaymentOut]:
    """지급 지시와 은행 회신 [모의]. 회신 전 지시도 빠지지 않게 바깥 조인한다."""
    rows = session.execute(
        select(PaymentOrder, BankReply)
        .outerjoin(BankReply, BankReply.payment_id == PaymentOrder.payment_id)
        .where(PaymentOrder.rebate_id == rebate_id)
        .order_by(PaymentOrder.payment_id)
    ).all()
    return [
        PaymentOut(
            payment_id=order.payment_id,
            amount_krw=order.amount_krw,
            status=order.status,
            ordered_by=order.ordered_by,
            ordered_at=order.ordered_at,
            bank_result=reply.result if reply is not None else None,
            bank_provenance=reply.provenance if reply is not None else None,
            replied_at=reply.replied_at if reply is not None else None,
        )
        for order, reply in rows
    ]


def _events(session: Session, rebate_id: str) -> list[EventLogOut]:
    """이 건의 상태 전이 이력. 같은 초에 여러 줄이 찍히므로 시각이 아니라 ID 순이다."""
    events = session.scalars(
        select(EventLog)
        .where(EventLog.entity_type == "rebate_claim", EventLog.entity_id == rebate_id)
        .order_by(EventLog.event_id)
    ).all()
    return [EventLogOut.model_validate(event) for event in events]
