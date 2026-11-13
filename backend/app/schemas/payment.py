"""지급 지시 · 은행 회신 요청과 결과.

역할은 문자열로 받는다. 재무가 아닌 역할은 형식 오류(422)가 아니라 권한 부족(403)이다.
은행 회신 결과에 출처('모의')를 담아 화면(14)이 [모의] 배지를 붙이게 한다.
"""

from pydantic import BaseModel, Field

from app.models.enums import BankResult


class PaymentOrderRequest(BaseModel):
    actor: str = Field(min_length=1, examples=["이재무"])
    role: str = Field(min_length=1, examples=["재무"])


class PaymentOrderResult(BaseModel):
    payment_id: int
    rebate_id: str
    amount_krw: int
    status: str
    claim_status: str


class BankReplyRequest(BaseModel):
    result: BankResult


class BankReplyResult(BaseModel):
    payment_id: int
    result: str
    provenance: str
    claim_status: str
