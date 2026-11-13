/**
 * 이벤트 이력 표: 언제 · 누가 · 이전 → 이후 상태 · 왜 · 함께 남긴 값.
 * 전체 이력 화면(15)은 showClaim 으로 건 ID 열을 켠다. 건 상세(14)는 끈 채로 쓴다.
 */
import { Link } from 'react-router'
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

type Props = {
  events: EventLogItem[]
  /** 건 ID 열을 보일지. 여러 건의 이력을 한 표에 섞을 때만 켠다. */
  showClaim?: boolean
}

export default function EventTimeline({ events, showClaim = false }: Props) {
  if (events.length === 0) {
    return <p className="muted">아직 이력이 없습니다.</p>
  }
  return (
    <div className="table-scroll">
      <table className="claim-table">
        <thead>
          <tr>
            {showClaim && <th>건 ID</th>}
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
              {showClaim && (
                <td>
                  <Link to={`/claims/${event.entity_id}`}>{event.entity_id}</Link>
                </td>
              )}
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
