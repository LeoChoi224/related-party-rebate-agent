/**
 * 소명 타입: 소명 요청 · 회신 [모의] · 주장별 대조 결과. 백엔드 schemas/explanation.py 와 맞춘다.
 */
import type {
  CheckVerdict,
  ClaimStatus,
  ExplanationJudgement,
  ExplanationStatus,
  Provenance,
} from './enums.ts'

/** 회신 속 주장 하나와 데이터 대조 결과 [주장]. 근거 행은 도구가 실제로 돌려준 것만 남는다. */
export type ExplanationCheck = {
  check_id: number
  seq: number
  claim_text: string
  verdict: CheckVerdict
  finding: string
  tool_used: string[]
  /** "파일:행" */
  evidence_ref: string[]
}

/** 회신과 AI 판단 · 사람 확인. AI 판단이 없으면(검토 전 · 대체 모드) ai_* 가 비어 있다. */
export type ExplanationReply = {
  reply_id: number
  raw_text: string
  provenance: Provenance
  ai_judgement: ExplanationJudgement | null
  ai_rationale: string[]
  missing_evidence: string[]
  follow_up_request: string | null
  ai_confidence: number | null
  verified: boolean
  fallback_used: boolean
  model: string | null
  review_result: ExplanationJudgement | null
  review_reason: string | null
  reviewed_by: string | null
  reviewed_at: string | null
  /** AI 판단이 없으면 비교할 것이 없어 null */
  agreed: boolean | null
  created_at: string
  checks: ExplanationCheck[]
}

export type Explanation = {
  exp_id: number
  rebate_id: string
  requested_items: string[]
  status: ExplanationStatus
  requested_by: string
  created_at: string
  reply: ExplanationReply | null
}

export type ExplanationConfirmBody = {
  judgement: ExplanationJudgement
  reason: string
  actor: string
  role: string
}

export type ExplanationConfirmResult = {
  reply_id: number
  judgement: ExplanationJudgement
  claim_status: ClaimStatus
}
