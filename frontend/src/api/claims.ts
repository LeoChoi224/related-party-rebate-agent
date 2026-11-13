/**
 * 장려금 건 API: 처리함 목록, 대상월 접수.
 * 건 상세 · 결정 · 지급 호출은 14 에서 더한다.
 */
import type { ClaimStatus } from '../types/enums.ts'
import type { ClaimListItem, IntakeResult } from '../types/rebate.ts'
import { api } from './client.ts'

/** 고른 상태의 건 목록(건 ID 순). 빈 배열이면 전체. */
export function listClaims(statuses: readonly ClaimStatus[]): Promise<ClaimListItem[]> {
  const params = new URLSearchParams()
  // set 은 같은 이름을 덮어써 마지막 하나만 남는다. 서버는 ?status=A&status=B 를 받는다.
  for (const status of statuses) {
    params.append('status', status)
  }
  const query = params.toString()
  return api.get<ClaimListItem[]>(query === '' ? '/claims' : `/claims?${query}`)
}

/** 대상월(YYYY-MM)의 장려금 건을 모두 접수해 전결대기 · 상신대기로 보낸다. */
export function intakePeriod(period: string): Promise<IntakeResult> {
  return api.post<IntakeResult>(`/claims/intake?${new URLSearchParams({ period })}`)
}
