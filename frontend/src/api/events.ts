/**
 * 이력 API: 모든 건의 상태 전이를 최신순으로.
 * AI 추천 기록 · 일치율은 17 · 25 에서 더한다.
 */
import type { EventLogItem } from '../types/eventLog.ts'
import { api } from './client.ts'

export type EventFilter = {
  rebateId: string
  actorRole: string
}

/** 건 ID · 처리자 역할로 거른 이력(최신순). 빈 글자인 조건은 보내지 않는다. */
export function listEvents(filter: EventFilter): Promise<EventLogItem[]> {
  const params = new URLSearchParams()
  // 사람이 친 건 ID 는 앞뒤 공백이 섞인다. 그대로 보내면 서버가 "그런 건 없음"으로 빈 목록을 준다.
  const rebateId = filter.rebateId.trim()
  if (rebateId !== '') {
    params.set('rebate_id', rebateId)
  }
  if (filter.actorRole !== '') {
    params.set('actor_role', filter.actorRole)
  }
  const query = params.toString()
  return api.get<EventLogItem[]>(query === '' ? '/events' : `/events?${query}`)
}
