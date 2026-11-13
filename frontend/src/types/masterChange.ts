/**
 * 마스터 정정 신고 타입. 백엔드 schemas/master_change.py 와 맞춘다.
 */
import type { ClaimStatus, ApproverRole } from './enums.ts'
import type { RelationEdge } from './relatedParty.ts'

/** 신고로 고칠 수 있는 속성. 실입금계좌는 돈이 들어온 사실이라 고칠 수 없다. */
export const CORRECTABLE_ATTRS = ['대표자', '주소', '등록계좌'] as const
export type CorrectableAttr = (typeof CORRECTABLE_ATTRS)[number]

export type MasterChangeBody = {
  attr_type: CorrectableAttr
  new_value: string
  /** 비우면 서버의 오늘 날짜(YYYY-MM-DD) */
  effective_date: string | null
  reported_text: string
  actor: string
  role: string
}

export type MasterChangeItem = {
  change_id: number
  agency_id: string
  attr_type: string
  old_value: string
  new_value: string
  effective_date: string
  reported_text: string | null
  reported_by: string
  /** 대리점이 신고한 값이라 [주장] */
  provenance: string
  created_at: string
}

export type GroupItem = {
  label: string
  members: string[]
}

/** 정정으로 판정 단위가 바뀐 건 하나. 재판정 전(재검토필요로 남음)이면 *_after 가 null */
export type ClaimImpact = {
  rebate_id: string
  agency_id: string
  period_ym: string
  from_status: ClaimStatus
  to_status: ClaimStatus
  min_authority_before: ApproverRole | null
  min_authority_after: ApproverRole | null
  group_sum_before: number | null
  group_sum_after: number | null
  approval_request_id: number | null
}

export type MasterChangeResult = {
  change: MasterChangeItem
  version_no_before: number
  version_no_after: number
  groups_before: GroupItem[]
  groups_after: GroupItem[]
  /** 같은 구성원으로 묶인 그룹이 그대로면 true(결론 유지) */
  group_retained: boolean
  affected_agencies: string[]
  /** 정정한 대리점이 낀 새 버전의 일치 쌍 */
  evidence: RelationEdge[]
  claims: ClaimImpact[]
}

export type RejudgeResult = {
  rebate_id: string
  status: ClaimStatus
  min_authority: ApproverRole | null
  group_sum_krw: number | null
  approval_request_id: number | null
}

/** 신고 문장 한 건과 AI 해석 [주장] · 영업지원팀 확인(19). 해석 전 · 대체 모드면 ai_* 가 null */
export type MasterChangeReport = {
  report_id: number
  raw_text: string
  provenance: string
  reported_by: string
  status: '확인대기' | '적용' | '기각'
  ai_agency_id: string | null
  ai_attr_type: CorrectableAttr | null
  ai_new_value: string | null
  ai_effective_date: string | null
  ai_confidence: number | null
  /** 가드가 찾은 문제 · 대체 모드 이유 */
  problems: string[]
  verified: boolean
  fallback_used: boolean
  model: string | null
  change_id: number | null
  decision_reason: string | null
  decided_by: string | null
  decided_at: string | null
  /** AI 해석과 같은 값으로 적용했는지. 기각 · 대체 모드면 null */
  agreed: boolean | null
  created_at: string
}

/** 영업지원팀 확인. 적용이면 대리점 · 속성 · 새 값, 기각이면 사유가 필요하다(서버 422). */
export type ReportDecisionBody = {
  apply: boolean
  agency_id: string
  attr_type: CorrectableAttr | null
  new_value: string
  effective_date: string | null
  reason: string
  actor: string
  role: string
}

export type ReportDecisionResult = {
  report: MasterChangeReport
  /** 적용이면 정정 적용 결과, 기각이면 null */
  result: MasterChangeResult | null
}
