/**
 * 처리함 페이지.
 * 지금 역할이 처리할 장려금 건 목록. 처음에는 역할의 기본 상태 필터(RoleContext 의 inbox)로 거르고,
 * 사용자가 상태를 바꿔 볼 수 있다. 서버가 준 값만 보여 주고, 합산 · 결재권자를 다시 계산하지 않는다.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../api/client.ts'
import { listClaims } from '../api/claims.ts'
import StatusBadge from '../components/StatusBadge.tsx'
import { useRole } from '../context/RoleContext.tsx'
import { ClaimStatus } from '../types/enums.ts'
import type { ClaimListItem } from '../types/rebate.ts'
import { formatKrw } from '../utils/format.ts'

const ALL_STATUSES = Object.values(ClaimStatus)

export default function InboxPage() {
  const { role, inbox } = useRole()
  // 처리함(/)에서 역할을 바꾸면 같은 주소라 페이지가 그대로 남는다.
  // key 가 바뀌면 React 가 목록을 새로 만들어, 필터가 새 역할의 기본값으로 돌아간다.
  return <InboxList key={role} role={role} initial={inbox} />
}

function InboxList({ role, initial }: { role: string; initial: readonly ClaimStatus[] }) {
  const [selected, setSelected] = useState<ClaimStatus[]>(() => [...initial])
  const [claims, setClaims] = useState<ClaimListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // 필터를 빨리 바꾸면 이전 요청의 응답이 늦게 올 수 있다. 정리 함수가 그 응답을 버린다.
    let ignore = false
    listClaims(selected)
      .then((items) => {
        if (ignore) return
        setClaims(items)
        setError(null)
      })
      .catch((e: unknown) => {
        if (ignore) return
        setError(
          e instanceof ApiError ? e.message : `요청을 보내지 못했습니다: ${String(e)}`,
        )
      })
    return () => {
      ignore = true
    }
  }, [selected])

  /** 상태 하나를 켜거나 끈다. 새 배열을 만들고, 순서는 상태 표 순서로 고정한다. */
  function toggle(status: ClaimStatus) {
    const next = selected.includes(status)
      ? selected.filter((s) => s !== status)
      : [...selected, status]
    setSelected(ALL_STATUSES.filter((s) => next.includes(s)))
  }

  return (
    <section>
      <h2>처리함 — {role}</h2>

      <div className="status-filter">
        {ALL_STATUSES.map((status) => (
          <label key={status}>
            <input
              type="checkbox"
              checked={selected.includes(status)}
              onChange={() => toggle(status)}
            />
            {status}
          </label>
        ))}
        <button type="button" onClick={() => setSelected([])}>
          전체
        </button>
      </div>
      <p className="muted">고른 상태가 없으면 전체를 보여 줍니다.</p>

      {error !== null && <p className="error">{error}</p>}
      {claims === null ? (
        error === null && <p>불러오는 중…</p>
      ) : claims.length === 0 ? (
        <p className="muted">
          처리할 건이 없습니다. 6월분은 시연 관리자 역할의 시연 패널에서 접수합니다.
        </p>
      ) : (
        <>
          <p>{claims.length}건</p>
          <div className="table-scroll">
            <table className="claim-table">
              <thead>
                <tr>
                  <th>건 ID</th>
                  <th>대리점</th>
                  <th>대상월</th>
                  <th>장려금액</th>
                  <th>상태</th>
                  <th>최소 결재권자</th>
                  <th>그룹</th>
                  <th>판정 단위 합산</th>
                </tr>
              </thead>
              <tbody>
                {claims.map((claim) => (
                  <tr key={claim.rebate_id}>
                    <td>
                      <Link to={`/claims/${claim.rebate_id}`}>{claim.rebate_id}</Link>
                    </td>
                    <td>
                      {claim.agency_id} · {claim.agency_name}
                    </td>
                    <td>{claim.period_ym}</td>
                    <td className="num">{formatKrw(claim.rebate_amount_krw)}</td>
                    <td>
                      <StatusBadge status={claim.status} />
                    </td>
                    <td>{claim.min_authority ?? '판정 전'}</td>
                    <td>
                      {/* 판정 전이면 그룹을 모른다. 단독이라 쓰면 G1 의 1~5월 건도 단독으로 보인다. */}
                      {claim.group_label ?? (claim.group_sum_krw === null ? '—' : '단독')}
                    </td>
                    <td className="num">
                      {claim.group_sum_krw === null ? '—' : formatKrw(claim.group_sum_krw)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted">
            장려금액은 [원본], 그룹 · 판정 단위 합산 · 최소 결재권자는 코드 계산(관련자 판정 ·
            한도 판정)입니다.
          </p>
        </>
      )}
    </section>
  )
}
