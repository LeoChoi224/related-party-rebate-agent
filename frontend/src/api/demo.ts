/**
 * 시연 패널 API: 초기화와 시나리오 이벤트 일괄 처리(26).
 * 정정 신고 · G1 결정 · 소명 회신은 업무 API(agencies · approvals · explanations)를 그대로 쓴다.
 */
import type { BankResult } from '../types/enums.ts'
import type { BankRepliesResult, ResetResult, StandaloneBatchResult } from '../types/demo.ts'
import { api } from './client.ts'

/** 업무 DB 를 원본으로 되돌린다. */
export function resetDemo(): Promise<ResetResult> {
  return api.post<ResetResult>('/demo/reset')
}

/** 대상월 단독 전결대기 건을 전결 승인 + 지급 지시까지 한 번에. G1 등 그룹 건은 건드리지 않는다. */
export function approveStandalone(periodYm: string): Promise<StandaloneBatchResult> {
  return api.post<StandaloneBatchResult>('/demo/events/standalone-approve', {
    period_ym: periodYm,
  })
}

/** 회신대기 지급 지시 전부에 은행 회신 [모의] 을 넣는다. */
export function replyAllPayments(result: BankResult): Promise<BankRepliesResult> {
  return api.post<BankRepliesResult>('/demo/events/bank-replies', { result })
}
