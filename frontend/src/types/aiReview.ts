/**
 * AI 추천 패널 타입. 백엔드 schemas/ai_recommendation.py 의 AiReviewOut 과 맞춘다.
 */
import type { ApproverRole, Decision, Recommendation } from './enums.ts'

export type AiReview = {
  rec_id: number
  /** "rebate_claim"(전결 건) 또는 "approval_request"(승인 요청) */
  target_type: string
  target_id: string
  /** 대체 모드면 null */
  recommendation: Recommendation | null
  rationale: string[]
  counter_evidence: string[]
  confidence: number | null
  /** 코드가 계산한 최소 결재권자. 실제 결재권자다. */
  min_authority: ApproverRole
  /** AI 가 낸 값 그대로. 코드 값보다 낮았으면 authority_raised */
  ai_authority: ApproverRole | null
  authority_raised: boolean
  verified: boolean
  fallback_used: boolean
  model: string | null
  human_decision: Decision | null
  human_reason: string | null
  /** 대체 모드면 비교할 추천이 없어 null */
  agreed: boolean | null
  decided_by: string | null
  decided_at: string | null
  created_at: string
}
