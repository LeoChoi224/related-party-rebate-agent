/**
 * 장려금 건 응답 타입. 백엔드 schemas/rebate.py 와 맞춘다.
 * 접수 결과, 처리함 목록 한 줄, 건 상세.
 */
import type { AiReview } from './aiReview.ts'
import type { ApprovalSummary } from './approval.ts'
import type { ApproverRole, ClaimStatus } from './enums.ts'
import type { EventLogItem } from './eventLog.ts'
import type { Explanation } from './explanation.ts'
import type { OffsetProposal } from './offset.ts'
import type { PaymentItem } from './payment.ts'
import type { RelationEdge } from './relatedParty.ts'

/** 대상월 접수 요약. 이름은 서버 JSON 그대로(snake_case) 둔다. */
export type IntakeResult = {
  period_ym: string
  received: number
  by_status: Record<string, number>
}

/** 처리함 목록 한 줄. 비어 있는 값은 JSON null 로 온다(필드는 항상 있다). */
export type ClaimListItem = {
  rebate_id: string
  agency_id: string
  agency_name: string
  period_ym: string
  rebate_amount_krw: number
  status: ClaimStatus
  /** 한도 판정 전이면 null */
  min_authority: ApproverRole | null
  /** 단독 대리점이면 null */
  group_label: string | null
  /** 한도 판정 전이면 null */
  group_sum_krw: number | null
}

/** 판정 단위(그룹 또는 단독 대리점)의 같은 달 건 하나. */
export type ClaimUnitMember = {
  rebate_id: string
  agency_id: string
  agency_name: string
  rebate_amount_krw: number
  status: ClaimStatus
}

/** 건 상세. 원본 기록, 코드 판정, 판정 근거, 승인 요청, 지급, 이력. */
export type ClaimDetail = {
  // 원본 기록 [원본]
  rebate_id: string
  agency_id: string
  agency_name: string
  period_ym: string
  sales_performance_krw: number
  rebate_amount_krw: number
  original_status: string
  original_approver: string | null
  /** "2026-06-15" 같은 날짜 글자. 원본이 NONE 이면 null */
  original_payment_date: string | null
  source_file: string
  source_row: number
  // 업무 상태와 코드 판정
  status: ClaimStatus
  min_authority: ApproverRole | null
  group_label: string | null
  group_sum_krw: number | null
  /** 규정 한도(서버 상수). 화면에 2,000,000 을 따로 적지 않는다. */
  limit_krw: number
  // 판정 근거와 그 뒤의 처리
  unit_claims: ClaimUnitMember[]
  evidence: RelationEdge[]
  approval: ApprovalSummary | null
  payments: PaymentItem[]
  events: EventLogItem[]
  /** 검토 단위(상신 건이면 승인 요청)의 가장 최근 AI 추천. 검토 전이면 null */
  ai_review: AiReview | null
  /** 이 건의 소명 요청들(요청 ID 순). 요청마다 회신 · AI 주장 대조 · 사람 확인이 붙는다. */
  explanations: Explanation[]
  /** 이 건의 상계 제안들(ID 순) [가정]. 그룹 건이 승인됐을 때 연체 채권이 있으면 생긴다. */
  offsets: OffsetProposal[]
  /** 지금 지급할 금액 = 장려금액 - 확정된 상계액 */
  payable_krw: number
}
