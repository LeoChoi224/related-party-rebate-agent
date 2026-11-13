/**
 * 지급 타입: 지급 지시 · 은행 회신 [모의]. 백엔드 schemas/payment.py 와 맞춘다.
 */
import type { BankResult, ClaimStatus, PaymentStatus, Provenance } from './enums.ts'

/** 건 상세의 지급 한 줄. 회신 전이면 은행 회신 칸이 null 이다. */
export type PaymentItem = {
  payment_id: number
  amount_krw: number
  status: PaymentStatus
  ordered_by: string
  ordered_at: string
  bank_result: BankResult | null
  bank_provenance: Provenance | null
  replied_at: string | null
}

export type PaymentOrderResult = {
  payment_id: number
  rebate_id: string
  amount_krw: number
  status: PaymentStatus
  claim_status: ClaimStatus
}

export type BankReplyResult = {
  payment_id: number
  result: BankResult
  provenance: Provenance
  claim_status: ClaimStatus
}
