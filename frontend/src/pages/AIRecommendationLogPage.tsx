/**
 * AI 추천 기록 페이지(25).
 * 세 AI(장려금 검토 · 소명 검토 · 상계 추천)의 출력과 사람 결정, 일치율, 대체 모드, 코드가 결재 단계를 올린 건.
 * 서버가 계산한 집계를 그대로 보여 주고 화면은 다시 계산하지 않는다.
 * 일치율의 분모는 AI 출력이 있고 사람이 결정한 건이다(대체 모드는 비교할 것이 없어 빠진다).
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { getAiLog } from '../api/aiRecommendations.ts'
import { ApiError } from '../api/client.ts'
import ProvenanceBadge from '../components/ProvenanceBadge.tsx'
import type { AiLog } from '../types/aiRecommendation.ts'
import { formatDateTime } from '../utils/format.ts'

function rate(value: number | null): string {
  return value === null ? '—' : `${Math.round(value * 100)}%`
}

export default function AIRecommendationLogPage() {
  const [log, setLog] = useState<AiLog | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false
    getAiLog()
      .then((data) => {
        if (!ignore) setLog(data)
      })
      .catch((e: unknown) => {
        if (!ignore) {
          setError(e instanceof ApiError ? e.message : `요청을 보내지 못했습니다: ${String(e)}`)
        }
      })
    return () => {
      ignore = true
    }
  }, [])

  if (log === null) {
    return error === null ? <p>불러오는 중…</p> : <p className="error">{error}</p>
  }

  return (
    <section>
      <h2>
        AI 추천 기록 <ProvenanceBadge provenance="주장" />
      </h2>
      <p className="muted">
        AI 는 판단 · 추천만 하고 결정은 사람이 합니다. AI 와 다르게 결정하려면 사유를 남겨야 합니다.
      </p>
      <div className="table-scroll">
        <table className="claim-table">
          <thead>
            <tr>
              <th>AI</th>
              <th>기록</th>
              <th>대체 모드</th>
              <th>사람 결정</th>
              <th>비교한 결정</th>
              <th>일치</th>
              <th>일치율</th>
              <th>결재 단계 올림</th>
            </tr>
          </thead>
          <tbody>
            {log.stats.map((s) => (
              <tr key={s.kind} className={s.kind === '전체' ? 'current-row' : undefined}>
                <td>{s.kind}</td>
                <td className="num">{s.total}</td>
                <td className="num">{s.fallback}</td>
                <td className="num">{s.decided}</td>
                <td className="num">{s.compared}</td>
                <td className="num">{s.agreed}</td>
                <td className="num">
                  <strong>{rate(s.agreement_rate)}</strong>
                </td>
                <td className="num">{s.authority_raised}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>기록(최신순)</h3>
      {log.rows.length === 0 ? (
        <p className="muted">아직 AI 기록이 없습니다. 건 상세에서 AI 검토 · AI 추천을 눌러 보세요.</p>
      ) : (
        <div className="table-scroll">
          <table className="claim-table">
            <thead>
              <tr>
                <th>시각</th>
                <th>AI</th>
                <th>대상</th>
                <th>AI 출력</th>
                <th>사람 결정</th>
                <th>일치</th>
                <th>사유</th>
                <th>모델</th>
              </tr>
            </thead>
            <tbody>
              {log.rows.map((r) => (
                <tr key={r.target + r.created_at}>
                  <td>{formatDateTime(r.created_at)}</td>
                  <td>{r.kind}</td>
                  <td>
                    {r.rebate_id === null ? (
                      r.target
                    ) : (
                      <Link to={`/claims/${r.rebate_id}`}>{r.target}</Link>
                    )}
                  </td>
                  <td>
                    {r.fallback_used ? (
                      <span className="badge badge-neutral">대체 모드</span>
                    ) : (
                      r.ai_output
                    )}
                    {r.authority_raised && <span className="badge badge-stop"> 결재 단계 올림</span>}
                  </td>
                  <td>{r.human_decision ?? '결정 전'}</td>
                  <td>
                    {r.agreed === null ? (
                      '—'
                    ) : (
                      <span className={`badge badge-${r.agreed ? 'ok' : 'stop'}`}>
                        {r.agreed ? '일치' : '불일치'}
                      </span>
                    )}
                  </td>
                  <td className="wrap">{r.human_reason ?? '—'}</td>
                  <td>{r.model ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
