/**
 * 시연 패널 페이지(시연 관리자 메뉴).
 * 지금은 초기화와 6월분 접수 두 버튼만 있다. 서버 응답(표별 행 수 · 상태별 건수)을 그대로 보여 준다.
 * 마스터 정정 신고 · 소명 회신 · 은행 회신 주입은 시나리오 이벤트를 만드는 26 에서 더한다.
 */
import { useState } from 'react'
import { ApiError } from '../api/client.ts'
import { intakePeriod } from '../api/claims.ts'
import { resetDemo } from '../api/demo.ts'

// 기준일(7/1)에 처리할 대상월. 원본에서 미지급 40건이 있는 달이다.
const INTAKE_PERIOD = '2026-06'

type Result = {
  title: string
  columns: [string, string]
  rows: Record<string, number>
}

export default function DemoPanelPage() {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<Result | null>(null)
  const [error, setError] = useState<string | null>(null)

  /** 요청 하나를 보내고 결과나 오류를 화면에 남긴다. 실패해도 버튼은 다시 눌린다. */
  async function run(action: () => Promise<Result>) {
    setBusy(true)
    setError(null)
    try {
      setResult(await action())
    } catch (e) {
      setResult(null)
      // 서버가 보낸 문장(409 "이미 처리된 건" 등)은 그대로, 서버에 닿지도 못한 오류는 원문을 붙인다.
      setError(e instanceof ApiError ? e.message : `요청을 보내지 못했습니다: ${String(e)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <h2>시연 패널</h2>
      <p>
        초기화는 업무 DB 를 원본으로 되돌립니다. 접수는 {INTAKE_PERIOD} 분 장려금 건을 전결대기 ·
        상신대기로 보냅니다.
      </p>
      <div className="actions">
        <button
          disabled={busy}
          onClick={() =>
            void run(async () => ({
              title: '초기화 완료',
              columns: ['표', '행 수'],
              rows: (await resetDemo()).counts,
            }))
          }
        >
          초기화
        </button>
        <button
          disabled={busy}
          onClick={() =>
            void run(async () => {
              const intake = await intakePeriod(INTAKE_PERIOD)
              return {
                title: `${intake.period_ym} 접수 ${intake.received}건`,
                columns: ['상태', '건수'],
                rows: intake.by_status,
              }
            })
          }
        >
          6월분 접수
        </button>
      </div>

      {error !== null && <p className="error">{error}</p>}
      {result !== null && (
        <>
          <h3>{result.title}</h3>
          <table>
            <thead>
              <tr>
                <th>{result.columns[0]}</th>
                <th>{result.columns[1]}</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(result.rows).map(([name, count]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td>{count.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  )
}
