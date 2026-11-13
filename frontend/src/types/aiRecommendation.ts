/**
 * AI 추천 기록 타입(25). 백엔드 schemas/ai_recommendation.py 의 AiLogRow · AiKindStats · AiLogOut 과 맞춘다.
 * 건 상세의 AI 패널 타입은 aiReview.ts 에 있다.
 */

/** AI 추천 기록 한 줄. 세 AI(장려금 검토 · 소명 검토 · 상계 추천)를 같은 모양으로 맞춘 것이다. */
export type AiLogRow = {
  kind: string
  /** "rebate_claim:RB-00006" · "approval_request:1" · "explanation_reply:1" · "offset_proposal:1" */
  target: string
  /** 건 상세로 이동할 건(승인 요청이면 포함 건 중 첫 건) */
  rebate_id: string | null
  /** 대체 모드면 null */
  ai_output: string | null
  human_decision: string | null
  human_reason: string | null
  /** 사람이 결정하기 전이거나 대체 모드면 null */
  agreed: boolean | null
  fallback_used: boolean
  authority_raised: boolean
  model: string | null
  created_at: string
}

/** AI 종류별 집계. agreement_rate = agreed / compared (비교한 결정이 없으면 null) */
export type AiKindStats = {
  kind: string
  total: number
  fallback: number
  decided: number
  compared: number
  agreed: number
  agreement_rate: number | null
  authority_raised: number
}

export type AiLog = {
  stats: AiKindStats[]
  rows: AiLogRow[]
}
