"""SQLAlchemy ORM 모델. docs/architecture.md 의 ERD 를 따른다.

Base.metadata.create_all() 은 import 된 모델만 테이블로 만든다.
새 모델을 만들면 반드시 여기에 추가한다.
"""

from app.models.agency import Agency, Deposit, IdentityAttribute
from app.models.ai_recommendation import AIRecommendation
from app.models.approval import ApprovalItem, ApprovalRequest
from app.models.base import Base
from app.models.event_log import EventLog
from app.models.explanation import (
    ExplanationCheck,
    ExplanationReply,
    ExplanationRequest,
)
from app.models.master_change import MasterChange, MasterChangeReport
from app.models.offset import OffsetProposal
from app.models.payment import BankReply, PaymentOrder
from app.models.rebate import RebateClaim
from app.models.receivable import ARAdjustment, ARItem
from app.models.related_party import (
    GroupMember,
    GroupVersion,
    RelatedGroup,
    RelationEdge,
)
from app.models.task import Task

__all__ = [
    "AIRecommendation",
    "ARAdjustment",
    "ARItem",
    "Agency",
    "ApprovalItem",
    "ApprovalRequest",
    "BankReply",
    "Base",
    "Deposit",
    "EventLog",
    "ExplanationCheck",
    "ExplanationReply",
    "ExplanationRequest",
    "GroupMember",
    "GroupVersion",
    "IdentityAttribute",
    "MasterChange",
    "MasterChangeReport",
    "OffsetProposal",
    "PaymentOrder",
    "RebateClaim",
    "RelatedGroup",
    "RelationEdge",
    "Task",
]
