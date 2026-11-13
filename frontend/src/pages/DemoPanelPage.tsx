/**
 * 시연 패널 페이지(시연 관리자 메뉴, 26).
 * 설계안 7장의 시나리오 3개를 진행할 이벤트를 버튼으로 넣는다. 각 버튼은 그 일을 맡은 부서의 시연 인물로
 * 업무 API 를 부르거나(정정 신고 · G1 결정 · 소명 회신), 여러 건을 한 번에 처리하는 시연 API 를 부른다
 * (단독 37건 전결 + 지급 지시, 은행 회신 일괄). 업무 규칙은 서버가 그대로 검사하고, 화면은 결과를 기록으로 남긴다.
 */
import { useState } from 'react'
import { Link } from 'react-router'
import { applyMasterChange } from '../api/agencies.ts'
import { decideApproval } from '../api/approvals.ts'
import { ApiError } from '../api/client.ts'
import { getClaim, intakePeriod } from '../api/claims.ts'
import { approveStandalone, replyAllPayments, resetDemo } from '../api/demo.ts'
import { sendExplanationReply } from '../api/explanations.ts'
import ProvenanceBadge from '../components/ProvenanceBadge.tsx'
import { BankResult, Decision, ExplanationStatus } from '../types/enums.ts'
import {
  DEMO_EXPLANATION_ITEMS,
  DEMO_REPLY,
  G1_JUNE_CLAIMS,
  MASTER_CHANGE_DEMOS,
} from '../utils/demoEvents.ts'
import { formatKrw } from '../utils/format.ts'

// 기준일(7/1)에 처리할 대상월. 원본에서 미지급 40건이 있는 달이다.
const INTAKE_PERIOD = '2026-06'
// 이벤트마다 그 일을 맡는 부서의 시연 인물(RoleContext 와 같은 이름).
const EXECUTIVE = { actor: '박임원', role: '영업임원' }
const SUPPORT = { actor: '김지원', role: '영업지원팀' }

type LogLine = { title: string; detail: string; ok: boolean }

/** G1 의 지금 승인 요청 번호. 재상신되면 새 요청이 생기므로 매번 건 상세에서 읽는다. */
async function g1RequestId(): Promise<number> {
  const approval = (await getClaim(G1_JUNE_CLAIMS[0])).approval
  if (approval === null) {
    throw new Error('G1 승인 요청이 없습니다. 먼저 6월분을 접수하세요.')
  }
  return approval.request_id
}

export default function DemoPanelPage() {
  const [busy, setBusy] = useState(false)
  const [log, setLog] = useState<LogLine[]>([])

  /** 이벤트 하나를 보내고 결과 · 오류를 기록 맨 위에 남긴다. 실패해도 버튼은 다시 눌린다. */
  async function run(title: string, action: () => Promise<string>) {
    setBusy(true)
    try {
      const detail = await action()
      setLog((lines) => [{ title, detail, ok: true }, ...lines])
    } catch (e) {
      // 서버가 보낸 문장(409 "이미 처리된 건" 등)은 그대로, 서버에 닿지도 못한 오류는 원문을 붙인다.
      const detail =
        e instanceof ApiError ? e.message : `요청을 보내지 못했습니다: ${String(e)}`
      setLog((lines) => [{ title, detail, ok: false }, ...lines])
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <h2>시연 패널</h2>
      <p className="muted">
        버튼은 그 일을 맡은 부서(영업지원팀 · 영업임원 · 재무 · 외부 [모의])의 이름으로 업무 API 를 부릅니다.
        권한 · 상태 · 사유 검사는 사람이 화면에서 누를 때와 똑같이 서버가 합니다.
      </p>

      <div className="next-action">
        <h3>준비</h3>
        <div className="actions">
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void run('초기화', async () => {
                const { counts } = await resetDemo()
                return `원본으로 되돌림 — 장려금 ${counts.rebate_claim}건 · 표 ${Object.keys(counts).length}개`
              })
            }
          >
            초기화
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void run(`${INTAKE_PERIOD} 접수`, async () => {
                const intake = await intakePeriod(INTAKE_PERIOD)
                const parts = Object.entries(intake.by_status).map(([s, n]) => `${s} ${n}`)
                return `${intake.received}건 접수 — ${parts.join(' · ')}`
              })
            }
          >
            6월분 접수
          </button>
        </div>
      </div>

      <div className="next-action">
        <h3>시나리오 1 — 정상 지급 · 상계 검토</h3>
        <div className="actions">
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void run('단독 건 일괄 전결 · 지급 지시', async () => {
                const r = await approveStandalone(INTAKE_PERIOD)
                return `영업지원팀 전결 승인 · 재무 지급 지시 ${r.approved}건, ${formatKrw(r.total_krw)}`
              })
            }
          >
            단독 37건 전결 + 지급 지시
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void run('은행 회신 [모의]', async () => {
                const r = await replyAllPayments(BankResult.SUCCESS)
                const parts = Object.entries(r.by_claim_status).map(([s, n]) => `${s} ${n}`)
                return `${r.result} ${r.replied}건, ${formatKrw(r.total_krw)} — ${parts.join(' · ') || '기다리는 지시 없음'}`
              })
            }
          >
            대기 중 지급 모두 은행 회신 성공 <ProvenanceBadge provenance="모의" />
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void run('영업임원 G1 승인', async () => {
                const requestId = await g1RequestId()
                const r = await decideApproval(requestId, {
                  decision: Decision.APPROVE,
                  reason: '시연: 그룹 합산 확인 후 승인(시나리오 1)',
                  ...EXECUTIVE,
                })
                return `승인 요청 #${r.request_id} 승인 — ${r.rebate_ids.join(', ')}, 상계 제안 ${r.offset_ids.length}건`
              })
            }
          >
            영업임원 G1 승인
          </button>
        </div>
        <p className="muted">
          G1 승인 뒤에는 <Link to={`/claims/${G1_JUNE_CLAIMS[0]}`}>{G1_JUNE_CLAIMS[0]}</Link> 상세의
          상계 검토 칸에서 영업 의견 · AI 추천 · 재무 결정 · 대리점 동의를 이어 갑니다.
        </p>
      </div>

      <div className="next-action">
        <h3>시나리오 2 — 마스터 정정 신고</h3>
        <div className="actions">
          {MASTER_CHANGE_DEMOS.map((demo) => (
            <button
              key={demo.agencyId}
              type="button"
              disabled={busy}
              onClick={() =>
                void run(`정정 신고 ${demo.label}`, async () => {
                  const r = await applyMasterChange(demo.agencyId, {
                    attr_type: demo.attrType,
                    new_value: demo.newValue,
                    effective_date: null,
                    reported_text: demo.reportedText,
                    ...SUPPORT,
                  })
                  const groups = r.groups_after
                    .map((g) => `${g.label}(${g.members.join('·')})`)
                    .join(', ')
                  return r.group_retained
                    ? `그룹 유지 — 근거 쌍 ${r.evidence.length}개, 영향 건 0 · 지금 그룹 ${groups}`
                    : `그룹 변경 — 지금 그룹 ${groups}, 다시 판정된 건 ${r.claims.length}건`
                })
              }
            >
              {demo.label}
            </button>
          ))}
        </div>
        <p className="muted">
          D-041 정정은 시나리오 1 의 단독 일괄 전결보다 먼저 넣어야 D-034 · D-041 6월분이 새 그룹 G2 로 다시
          판정되는 것이 보입니다(이미 지급된 건은 다시 판정하지 않습니다). 결과 자세히 보기:{' '}
          <Link to="/master-changes">정정 신고</Link> 화면의 이력.
        </p>
      </div>

      <div className="next-action">
        <h3>시나리오 3 — 반려 · 소명 · 재상신</h3>
        <div className="actions">
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void run('영업임원 G1 반려 + 소명 요청', async () => {
                const requestId = await g1RequestId()
                const r = await decideApproval(requestId, {
                  decision: Decision.REJECT,
                  reason: '소명 먼저: D-024 와 계좌가 겹친 경위 확인 필요',
                  explanation_items: DEMO_EXPLANATION_ITEMS,
                  ...EXECUTIVE,
                })
                return `승인 요청 #${r.request_id} 반려 — 소명 요청 ${r.explanation_ids.length}건`
              })
            }
          >
            영업임원 G1 반려 + 소명 요청
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void run('소명 회신 [모의]', async () => {
                const sent: string[] = []
                for (const rebateId of G1_JUNE_CLAIMS) {
                  const waiting = (await getClaim(rebateId)).explanations.filter(
                    (e) => e.status === ExplanationStatus.AWAITING_REPLY,
                  )
                  for (const exp of waiting) {
                    await sendExplanationReply(exp.exp_id, DEMO_REPLY)
                    sent.push(`${rebateId} #${exp.exp_id}`)
                  }
                }
                return sent.length === 0
                  ? '회신을 기다리는 G1 소명 요청이 없습니다'
                  : `회신 등록 ${sent.length}건(${sent.join(', ')}) — AI 소명 검토가 함께 돌았습니다`
              })
            }
          >
            G1 소명 회신 넣기 <ProvenanceBadge provenance="모의" />
          </button>
        </div>
        <p className="muted">
          회신 문구: “{DEMO_REPLY}” — 회신마다 AI 소명 검토가 돌아 키가 있으면 건당 수십 초 걸립니다(그동안
          버튼이 잠깁니다). 확인은 각 건 상세의 소명 칸에서 영업지원팀이 합니다.
        </p>
      </div>

      <h3>기록</h3>
      {log.length === 0 ? (
        <p className="muted">아직 넣은 이벤트가 없습니다.</p>
      ) : (
        <ul>
          {log.map((line, index) => (
            <li key={log.length - index} className={line.ok ? undefined : 'error'}>
              <strong>{line.title}</strong> — {line.detail}
            </li>
          ))}
        </ul>
      )}
      {busy && <p className="muted">처리 중…</p>}
    </section>
  )
}
