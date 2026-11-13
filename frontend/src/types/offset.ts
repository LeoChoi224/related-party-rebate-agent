/**
 * 상계 타입 [가정]: 상계 제안, 연체 채권, 잔액 조정, 영업 의견 · 재무 결정 · 대리점 동의 요청.
 * 백엔드 schemas/offset.py 와 맞춘다.
 */
import type {
  AgencyConsent,
  ClaimStatus,
  Decision,
  OffsetStatus,
  Provenance,
  SalesAlternative,
} from './enums.ts'

/** 상계 대상 연체 채권 한 줄. remaining_krw = 원본 잔액 - 상계 조정 합계 */
export type OverdueItem = {
  ar_id: string
  agency_id: string
  due_date: string
  aging_days: number
  outstanding_krw: number
  remaining_krw: number
  source_file: string
  source_row: number
}

export type ArAdjustment = {
  ar_id: string
  amount_krw: number
  provenance: Provenance
  applied_at: string
}

/** 상계 제안 하나. 상계 한도는 코드가 계산하고 AI 추천 · 재무 결정은 그 안에서만 고른다. */
export type OffsetProposal = {
  offset_id: number
  rebate_id: string
  group_label: string
  overdue_total_krw: number
  max_offset_krw: number
  status: OffsetStatus
  /** 영업 의견 [주장](23). 입력 전이면 null */
  sales_alternative: SalesAlternative | null
  sales_amount_krw: number | null
  sales_opinion: string | null
  sales_by: string | null
  sales_at: string | null
  ai_amount_krw: number | null
  ai_rationale: string[]
  ai_counter_evidence: string[]
  ai_confidence: number | null
  verified: boolean
  fallback_used: boolean
  model: string | null
  finance_decision: Decision | null
  offset_amount_krw: number | null
  finance_reason: string | null
  decided_by: string | null
  decided_at: string | null
  agreed: boolean | null
  /** 재무 결정이 영업 대안과 같은지. 영업 의견이 없으면 null */
  sales_followed: boolean | null
  /** 지급 후 회수 약정 기한("2026-09-30"). 없으면 null */
  collection_due_date: string | null
  agency_consent: AgencyConsent | null
  consent_provenance: Provenance | null
  consented_at: string | null
  created_at: string
  overdue_items: OverdueItem[]
  adjustments: ArAdjustment[]
}

/** 재무 결정 본문. 승인이면 상계액, 반려(상계하지 않음)면 사유가 필요하다(서버 422). */
export type OffsetDecisionBody = {
  decision: Decision
  offset_amount_krw: number | null
  reason: string
  actor: string
  role: string
  /** 상계하지 않으면서 넣으면 지급 후 회수 약정 */
  collection_due_date: string | null
}

/** 영업 의견 본문. 부분 상계면 상계액이 필요하다(서버 422). */
export type SalesOpinionBody = {
  alternative: SalesAlternative
  amount_krw: number | null
  opinion: string
  actor: string
  role: string
}

export type OffsetResult = {
  offset: OffsetProposal
  claim_status: ClaimStatus
  payable_krw: number
}
