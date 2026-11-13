/**
 * 결재 타입: 결정 요청 · 결과, 건 상세의 승인 요청 칸. 백엔드 schemas/approval.py 와 맞춘다.
 */
import type { ApproverRole, ClaimStatus, Decision } from './enums.ts'

/** 전결 결정 · 승인 요청 결정의 요청 본문. 역할은 서버가 403 을 내도록 문자열로 보낸다. */
export type DecisionRequest = {
  decision: Decision
  reason: string
  actor: string
  role: string
}

export type ClaimDecisionResult = {
  rebate_id: string
  status: ClaimStatus
}

export type ApprovalDecisionResult = {
  request_id: number
  decision: Decision
  decided_by: string
  rebate_ids: string[]
}

/** 건 상세의 승인 요청 칸. 결정 전에는 결정 · 사유 · 결정자 · 시각이 null 이다. */
export type ApprovalSummary = {
  request_id: number
  approver_role: ApproverRole
  group_sum_krw: number
  decision: Decision | null
  reason: string | null
  decided_by: string | null
  decided_at: string | null
  /** 이 요청을 결정하면 함께 바뀌는 건 */
  rebate_ids: string[]
}
