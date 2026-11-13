/**
 * 마스터 정정 신고 API: 정정 신고 적용(그룹 재계산 · 영향 건 재판정), 정정 이력,
 * 신고 문장 AI 해석과 영업지원팀 확인(19).
 */
import type {
  MasterChangeBody,
  MasterChangeItem,
  MasterChangeReport,
  MasterChangeResult,
  ReportDecisionBody,
  ReportDecisionResult,
} from '../types/masterChange.ts'
import { api } from './client.ts'

/** 정정을 적용한다. 영업지원팀이 아니면 403, 없는 대리점 404, 같은 값 · 빈 값 등은 422. */
export function applyMasterChange(
  agencyId: string,
  body: MasterChangeBody,
): Promise<MasterChangeResult> {
  return api.post<MasterChangeResult>(
    `/agencies/${encodeURIComponent(agencyId)}/master-changes`,
    body,
  )
}

/** 정정 신고 이력(최신순) */
export function listMasterChanges(): Promise<MasterChangeItem[]> {
  return api.get<MasterChangeItem[]>('/master-changes')
}

/** 신고 문장을 AI 가 해석한다(LLM 을 부르므로 몇 초 걸릴 수 있음). 영업지원팀이 아니면 403. */
export function createMasterChangeReport(
  rawText: string,
  actor: string,
  role: string,
): Promise<MasterChangeReport> {
  return api.post<MasterChangeReport>('/master-change-reports', { raw_text: rawText, actor, role })
}

/** 해석을 확인 · 수정해 적용하거나 기각한다. AI 와 다른 값에 사유가 없으면 422, 이미 확인했으면 409. */
export function decideMasterChangeReport(
  reportId: number,
  body: ReportDecisionBody,
): Promise<ReportDecisionResult> {
  return api.post<ReportDecisionResult>(`/master-change-reports/${reportId}/decision`, body)
}
