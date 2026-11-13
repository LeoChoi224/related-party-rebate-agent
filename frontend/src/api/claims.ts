/**
 * 장려금 건 API. 지금은 대상월 접수만 있다.
 * 처리함 목록 · 건 상세 · 결정 · 지급 호출은 13 · 14 에서 더한다.
 */
import type { IntakeResult } from '../types/rebate.ts'
import { api } from './client.ts'

/** 대상월(YYYY-MM)의 장려금 건을 모두 접수해 전결대기 · 상신대기로 보낸다. */
export function intakePeriod(period: string): Promise<IntakeResult> {
  return api.post<IntakeResult>(`/claims/intake?${new URLSearchParams({ period })}`)
}
