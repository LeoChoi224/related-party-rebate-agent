/**
 * 이벤트 이력 페이지.
 * 모든 건의 상태 변경을 최신순으로: 누가, 언제, 무엇을, 이전 상태에서 어떤 상태로, 왜.
 * 건 ID · 처리자 역할로 거른다. 조회 버튼(엔터)을 눌러야 요청이 나간다.
 */
import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client.ts'
import { listEvents, type EventFilter } from '../api/events.ts'
import EventTimeline from '../components/EventTimeline.tsx'
import type { EventLogItem } from '../types/eventLog.ts'

// 이력에 실제로 찍히는 처리자 역할. "시스템"은 services/intake.py 의 SYSTEM_ACTOR,
// "모의 외부"는 mocks/bank.py 의 BANK_ROLE 과 글자가 같아야 한다.
// 시연 관리자는 상태를 바꾸지 않아 이력을 남기지 않는다.
const ACTOR_ROLES = ['시스템', '영업지원팀', '영업임원', '재무', '모의 외부'] as const

const EMPTY_FILTER: EventFilter = { rebateId: '', actorRole: '' }

export default function EventLogPage() {
  // 입력 중인 값과 실제로 조회한 값을 나눈다. 글자를 칠 때마다 요청이 나가지 않게 한다.
  const [rebateInput, setRebateInput] = useState('')
  const [roleInput, setRoleInput] = useState('')
  const [filter, setFilter] = useState<EventFilter>(EMPTY_FILTER)
  const [events, setEvents] = useState<EventLogItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false
    listEvents(filter)
      .then((items) => {
        if (ignore) return
        setEvents(items)
        setError(null)
      })
      .catch((e: unknown) => {
        if (ignore) return
        setError(e instanceof ApiError ? e.message : `요청을 보내지 못했습니다: ${String(e)}`)
      })
    return () => {
      ignore = true
    }
  }, [filter])

  function search(event: FormEvent<HTMLFormElement>) {
    // 폼 제출의 기본 동작(페이지 새로고침)을 막는다.
    event.preventDefault()
    setFilter({ rebateId: rebateInput, actorRole: roleInput })
  }

  function reset() {
    setRebateInput('')
    setRoleInput('')
    setFilter(EMPTY_FILTER)
  }

  return (
    <section>
      <h2>이벤트 이력</h2>
      <form className="toolbar" onSubmit={search}>
        <label>
          건 ID{' '}
          <input
            value={rebateInput}
            placeholder="RB-00054"
            onChange={(event) => setRebateInput(event.target.value)}
          />
        </label>
        <label>
          처리자 역할{' '}
          <select value={roleInput} onChange={(event) => setRoleInput(event.target.value)}>
            <option value="">전체</option>
            {ACTOR_ROLES.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
        </label>
        <button type="submit">조회</button>
        <button type="button" onClick={reset}>
          초기화
        </button>
        {events !== null && <span>{events.length}건 · 최신순</span>}
      </form>

      {error !== null && <p className="error">{error}</p>}
      {events === null ? (
        error === null && <p>불러오는 중…</p>
      ) : (
        <EventTimeline events={events} showClaim />
      )}
    </section>
  )
}
