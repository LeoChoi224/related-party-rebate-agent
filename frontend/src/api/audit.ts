/**
 * 감사 API(24): 과거 지급 건 사후 검토 실행.
 */
import type { RetroReviewResult } from '../types/audit.ts'
import { api } from './client.ts'

/** 원본 지급 건을 지금 그룹으로 다시 판정해 위반 건마다 감사 작업을 연다. 내부감사가 아니면 403. */
export function runRetroReview(actor: string, role: string): Promise<RetroReviewResult> {
  return api.post<RetroReviewResult>('/audit/retro-review', { actor, role })
}
