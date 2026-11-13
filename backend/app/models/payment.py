"""지급 지시와 은행 회신.

PaymentOrder: 재무가 낸 지급 지시. 금액은 장려금액에서 확정된 상계액을 뺀 남은 금액이다(22).
실제 수취계좌는 원본에 없어(설계안 2장) 지급 계좌 컬럼은 두지 않는다.
BankReply: 은행 회신 [모의](성공 · 계좌오류). 지시 하나에 회신은 하나이고,
계좌오류 뒤 다시 지급하면 새 지시를 만든다.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PaymentOrder(Base):
    __tablename__ = "payment_order"

    payment_id: Mapped[int] = mapped_column(primary_key=True)
    rebate_id: Mapped[str] = mapped_column(ForeignKey("rebate_claim.rebate_id"))
    amount_krw: Mapped[int]
    status: Mapped[str]
    ordered_by: Mapped[str]
    ordered_at: Mapped[datetime] = mapped_column(server_default=func.now())


class BankReply(Base):
    __tablename__ = "bank_reply"

    reply_id: Mapped[int] = mapped_column(primary_key=True)
    # 지시 하나에 회신 하나. 서비스 검사(409)를 거치지 않는 경로도 DB 가 막는다.
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payment_order.payment_id"), unique=True
    )
    result: Mapped[str]
    provenance: Mapped[str]
    replied_at: Mapped[datetime] = mapped_column(server_default=func.now())
