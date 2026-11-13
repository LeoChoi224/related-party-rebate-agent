/**
 * 이벤트 이력 타입. 백엔드 schemas/event_log.py 와 맞춘다.
 */
import type { ClaimStatus } from './enums.ts'

/** 건 상태 전이 한 줄. ts 는 UTC 표시("…Z")가 붙은 ISO 글자다. */
export type EventLogItem = {
  event_id: number
  ts: string
  actor: string
  actor_role: string
  from_status: ClaimStatus
  to_status: ClaimStatus
  reason: string
  /** 전이와 함께 남긴 값(그룹 합산 · 최소 결재권자 등). 없으면 null */
  payload: Record<string, unknown> | null
}
