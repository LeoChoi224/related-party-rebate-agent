/**
 * 이벤트 이력 표: 언제 · 누가 · 이전 → 이후 상태 · 왜 · 함께 남긴 값.
 */
import type { EventLogItem } from '../types/eventLog.ts'
import { formatDateTime } from '../utils/format.ts'
import StatusBadge from './StatusBadge.tsx'

/** payload 를 "키: 값 · 키: 값" 한 줄로. 숫자는 자릿수 쉼표, 빈 값은 null 그대로 보인다. */
function formatPayload(payload: Record<string, unknown> | null): string {
  if (payload === null) return ''
  return Object.entries(payload)
    .map(([key, value]) =>
      typeof value === 'number'
        ? `${key}: ${value.toLocaleString('ko-KR')}`
        : `${key}: ${String(value)}`,
    )
    .join(' · ')
}

export default function EventTimeline({ events }: { events: EventLogItem[] }) {
  if (events.length === 0) {
    return <p className="muted">아직 이력이 없습니다.</p>
  }
  return (
    <div className="table-scroll">
      <table className="claim-table">
        <thead>
          <tr>
            <th>시각</th>
            <th>처리자</th>
            <th>변경</th>
            <th>이유</th>
            <th>함께 남긴 값</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <tr key={event.event_id}>
              <td>{formatDateTime(event.ts)}</td>
              <td>
                {event.actor} · {event.actor_role}
              </td>
              <td>
                {event.from_status} → <StatusBadge status={event.to_status} />
              </td>
              <td>{event.reason}</td>
              <td className="muted">{formatPayload(event.payload)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
