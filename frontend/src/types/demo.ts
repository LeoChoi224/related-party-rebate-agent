/**
 * 시연 패널 타입(26). 백엔드 schemas/demo.py 와 맞춘다.
 */
import type { BankResult, ClaimStatus } from './enums.ts'

/** 초기화 결과: 표 이름별로 다시 채운 행 수. */
export type ResetResult = {
  counts: Record<string, number>
}

/** 단독 전결대기 건 일괄 전결 승인 · 지급 지시 결과 */
export type StandaloneBatchResult = {
  period_ym: string
  approved: number
  payment_ids: number[]
  total_krw: number
}

/** 회신대기 지급 지시 전부에 넣은 은행 회신 [모의] 결과 */
export type BankRepliesResult = {
  result: BankResult
  replied: number
  total_krw: number
  by_claim_status: Partial<Record<ClaimStatus, number>>
}
