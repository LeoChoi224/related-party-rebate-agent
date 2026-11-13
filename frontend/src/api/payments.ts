/**
 * 지급 API: 은행 회신 [모의] 넣기.
 * 지급 지시는 건에 대한 행동이라 claims.ts 에 있다(백엔드 라우터와 같은 나눔).
 */
import type { BankResult } from '../types/enums.ts'
import type { BankReplyResult } from '../types/payment.ts'
import { api } from './client.ts'

/** 은행 회신을 시연으로 넣는다. 성공이면 지급완료, 계좌오류면 지급보류. 두 번째 회신은 409. */
export function sendBankReply(paymentId: number, result: BankResult): Promise<BankReplyResult> {
  return api.post<BankReplyResult>(`/payments/${paymentId}/bank-reply`, { result })
}
