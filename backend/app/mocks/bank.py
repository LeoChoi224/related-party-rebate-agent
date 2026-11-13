"""모의 은행 [모의].

회신 결과(성공 · 계좌오류)는 시연이 고른다. 이 모듈은 그 결과를 출처 '모의'로 기록만 한다.
진짜 은행 연동으로 바꾸면 이 모듈만 갈아끼운다.
"""

from sqlalchemy.orm import Session

from app.models import BankReply, PaymentOrder
from app.models.enums import BankResult, Provenance

# 이력에 남길 처리자. 설계안 4-4 의 "모의 외부" 주체.
BANK_ACTOR = "은행"
BANK_ROLE = "모의 외부"


def record_bank_reply(
    session: Session, payment: PaymentOrder, result: BankResult
) -> BankReply:
    """지급 지시에 대한 은행 회신을 출처 '모의'로 남긴다."""
    reply = BankReply(
        payment_id=payment.payment_id, result=result, provenance=Provenance.MOCK
    )
    session.add(reply)
    session.flush()
    return reply
