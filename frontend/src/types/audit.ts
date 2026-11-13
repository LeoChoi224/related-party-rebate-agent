/**
 * 감사 사후 검토 타입(24). 백엔드 schemas/audit.py 와 맞춘다.
 */
import type { ApproverRole } from './enums.ts'

/** 결재 단계가 모자랐던 지급 건 하나. task_id 는 이번 실행에서 새로 연 작업(이미 있으면 null). */
export type RetroFinding = {
  rebate_id: string
  agency_id: string
  period_ym: string
  group_label: string | null
  group_sum_krw: number
  min_authority: ApproverRole
  original_approver: string
  rebate_amount_krw: number
  original_payment_date: string | null
  task_id: number | null
}

/** checked = 다시 판정한 원본 지급 건 수, total_krw = 위반 건 지급액 합계 */
export type RetroReviewResult = {
  checked: number
  periods: string[]
  findings: RetroFinding[]
  total_krw: number
  created_tasks: number
}
