/**
 * 장려금 건 응답 타입. 백엔드 schemas/rebate.py 와 맞춘다.
 * 접수 결과와 처리함 목록 한 줄. 건 상세 타입은 14 에서 더한다.
 */
import type { ApproverRole, ClaimStatus } from './enums.ts'

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
