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
  /** 반려하면서 대리점에 소명을 요청할 항목. 반려된 건마다 소명 요청이 하나씩 생긴다. */
  explanation_items?: string[]
}

export type ClaimDecisionResult = {
  rebate_id: string
  status: ClaimStatus
  /** 반려와 함께 만든 소명 요청 */
  explanation_ids: number[]
  /** 승인 뒤 같은 그룹 연체 채권으로 만든 상계 제안 */
  offset_ids: number[]
}

export type ApprovalDecisionResult = {
  request_id: number
  decision: Decision
  decided_by: string
  rebate_ids: string[]
  explanation_ids: number[]
  offset_ids: number[]
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
