"""SQLAlchemy ORM 모델. docs/architecture.md 의 ERD 를 따른다.

Base.metadata.create_all() 은 import 된 모델만 테이블로 만든다.
새 모델을 만들면 반드시 여기에 추가한다.
"""

from app.models.agency import Agency, Deposit, IdentityAttribute
from app.models.base import Base
from app.models.rebate import RebateClaim
from app.models.receivable import ARItem

__all__ = [
    "ARItem",
    "Agency",
    "Base",
    "Deposit",
    "IdentityAttribute",
    "RebateClaim",
]
