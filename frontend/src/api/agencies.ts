/**
 * 마스터 정정 신고 API: 정정 신고 적용(그룹 재계산 · 영향 건 재판정), 정정 이력.
 */
import type {
  MasterChangeBody,
  MasterChangeItem,
  MasterChangeResult,
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
