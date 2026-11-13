/**
 * 건 상세의 상계 칸 [가정]: 같은 그룹 연체 채권, 영업 의견 [주장], AI 상계액 추천 [주장], 재무 결정,
 * 대리점 동의 [모의], 잔액 조정. 영업 의견은 대리점 관계 부담을 보고 고른 대안이다(23, 부서 영향).
 * 서버가 저장한 값을 그대로 보여 주고 상계 한도 · 잔액을 다시 계산하지 않는다.
 * 버튼은 제안 상태만 보고 보인다. 역할 권한은 서버가 403 으로 판단한다(14 결정).
 * 이 칸은 자기 오류 문장과 처리 중 표시를 따로 가진다. 성공하면 onChanged 로 상세를 다시 읽게 한다.
 */
import { useState, type ReactNode } from 'react'
import { ApiError } from '../api/client.ts'
import {
  decideOffset,
  recommendOffset,
  sendAgencyConsent,
  sendSalesOpinion,
} from '../api/offsets.ts'
import { useRole } from '../context/RoleContext.tsx'
import { AgencyConsent, Decision, OffsetStatus, SalesAlternative } from '../types/enums.ts'
import type { OffsetProposal } from '../types/offset.ts'
import type { ClaimDetail } from '../types/rebate.ts'
import { formatDateTime, formatKrw } from '../utils/format.ts'
import ProvenanceBadge from './ProvenanceBadge.tsx'

const STATUS_TONE: Record<OffsetStatus, string> = {
  재무검토: 'wait',
  동의대기: 'wait',
  상계확정: 'ok',
  재무반려: 'neutral',
  동의거절: 'neutral',
  취소: 'neutral',
}

type Props = {
  detail: ClaimDetail
  onChanged: () => void
}

export default function OffsetSection({ detail, onChanged }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (detail.offsets.length === 0) {
    return null
  }

  /** 행동 하나를 보내고, 성공하면 상세를 다시 읽고, 실패하면 서버 문장을 남긴다. */
  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await action()
      onChanged()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `요청을 보내지 못했습니다: ${String(e)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="detail-section">
      <h3>
        상계 검토 <ProvenanceBadge provenance="가정" />
      </h3>
      <p className="muted">
        관련자 그룹 건이 승인되면 같은 그룹의 90일 넘은 연체 채권과 장려금을 상계할지 봅니다.
        지금 지급할 금액: <strong>{formatKrw(detail.payable_krw)}</strong>
      </p>
      {detail.offsets.map((offset) => (
        <OffsetCard key={offset.offset_id} offset={offset} busy={busy} run={run} />
      ))}
      {error !== null && <p className="error">{error}</p>}
    </section>
  )
}

type RunProps = {
  busy: boolean
  run: (action: () => Promise<unknown>) => void
}

function OffsetCard({ offset, busy, run }: RunProps & { offset: OffsetProposal }) {
  const reviewed = offset.verified || offset.fallback_used
  return (
    <div className="next-action">
      <h4>
        상계 제안 #{offset.offset_id}{' '}
        <span className={`badge badge-${STATUS_TONE[offset.status]}`}>{offset.status}</span>
      </h4>
      <dl className="facts">
        <dt>그룹</dt>
        <dd>{offset.group_label}</dd>
        <dt>그룹 연체 잔액(제안 당시)</dt>
        <dd>{formatKrw(offset.overdue_total_krw)}</dd>
        <dt>상계 한도(코드 계산)</dt>
        <dd>{formatKrw(offset.max_offset_krw)}</dd>
      </dl>
      <OverdueTable offset={offset} />

      <h4>
        영업 의견 <ProvenanceBadge provenance="주장" />
      </h4>
      <SalesView offset={offset} />
      {offset.status === OffsetStatus.AWAITING_FINANCE && (
        <SalesForm offsetId={offset.offset_id} busy={busy} run={run} />
      )}

      <h4>
        AI 상계액 추천 <ProvenanceBadge provenance="주장" />
      </h4>
      {reviewed ? (
        <AiAdvice offset={offset} />
      ) : offset.status === OffsetStatus.AWAITING_FINANCE ? (
        <div className="actions">
          <button
            type="button"
            disabled={busy}
            onClick={() => run(() => recommendOffset(offset.offset_id))}
          >
            AI 추천
          </button>
          <span className="muted">LLM 을 부르므로 몇 초 걸릴 수 있습니다.</span>
        </div>
      ) : (
        <p className="muted">AI 추천 기록 없음</p>
      )}

      {offset.status === OffsetStatus.AWAITING_FINANCE ? (
        // AI 추천 · 영업 권고액이 바뀌면 입력칸 처음 값도 새 값으로 다시 채운다.
        <FinanceForm
          key={`${offset.ai_amount_krw ?? 'none'}-${offset.sales_amount_krw ?? 'none'}`}
          offset={offset}
          busy={busy}
          run={run}
        />
      ) : (
        <FinanceView offset={offset} />
      )}
      {offset.status === OffsetStatus.AWAITING_CONSENT && (
        <ConsentButtons offsetId={offset.offset_id} busy={busy} run={run} />
      )}
      {offset.agency_consent !== null && (
        <p className="muted">
          대리점 회신 <strong>{offset.agency_consent}</strong>{' '}
          {offset.consent_provenance !== null && (
            <ProvenanceBadge provenance={offset.consent_provenance} />
          )}
          {offset.consented_at !== null && ` · ${formatDateTime(offset.consented_at)}`}
        </p>
      )}
      {offset.adjustments.length > 0 && (
        <p>
          채권 잔액 조정 <ProvenanceBadge provenance="가정" />:{' '}
          {offset.adjustments.map((a) => `${a.ar_id} −${formatKrw(a.amount_krw)}`).join(', ')}
        </p>
      )}
    </div>
  )
}

function OverdueTable({ offset }: { offset: OffsetProposal }) {
  return (
    <div className="table-scroll">
      <table className="claim-table">
        <thead>
          <tr>
            <th>연체 채권(상계 순서)</th>
            <th>대리점</th>
            <th>연체일</th>
            <th>원본 잔액</th>
            <th>지금 잔액</th>
            <th>근거 행</th>
          </tr>
        </thead>
        <tbody>
          {offset.overdue_items.map((item) => (
            <tr key={item.ar_id}>
              <td>{item.ar_id}</td>
              <td>{item.agency_id}</td>
              <td className="num">{item.aging_days}일</td>
              <td className="num">{formatKrw(item.outstanding_krw)}</td>
              <td className="num">{formatKrw(item.remaining_krw)}</td>
              <td>
                {item.source_file}:{item.source_row} <ProvenanceBadge provenance="원본" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SalesView({ offset }: { offset: OffsetProposal }) {
  if (offset.sales_alternative === null) {
    return <p className="muted">영업 의견 없음 — 재무는 의견 없이도 결정할 수 있습니다.</p>
  }
  return (
    <p>
      <strong>{offset.sales_alternative}</strong>
      {offset.sales_amount_krw !== null && ` ${formatKrw(offset.sales_amount_krw)}`} —{' '}
      {offset.sales_opinion}{' '}
      <span className="muted">
        ({offset.sales_by}
        {offset.sales_at !== null && ` · ${formatDateTime(offset.sales_at)}`})
      </span>
    </p>
  )
}

function SalesForm({ offsetId, busy, run }: RunProps & { offsetId: number }) {
  const { role, actor } = useRole()
  const [alternative, setAlternative] = useState<SalesAlternative>(SalesAlternative.PARTIAL_OFFSET)
  const [amount, setAmount] = useState('')
  const [opinion, setOpinion] = useState('')
  const partial = alternative === SalesAlternative.PARTIAL_OFFSET

  return (
    <div className="decision-form">
      <h4>
        영업 의견 입력 <span className="muted">— 지금 역할: {role} · {actor}</span>
      </h4>
      <label>
        대안{' '}
        <select
          value={alternative}
          onChange={(event) => setAlternative(event.target.value as SalesAlternative)}
        >
          {Object.values(SalesAlternative).map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      {partial && (
        <label>
          권하는 상계액(원, 한도 미만){' '}
          <input type="number" min={1} value={amount} onChange={(event) => setAmount(event.target.value)} />
        </label>
      )}
      <label>
        의견(대리점 관계 부담)
        <textarea value={opinion} onChange={(event) => setOpinion(event.target.value)} />
      </label>
      <div className="actions">
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            run(() =>
              sendSalesOpinion(offsetId, {
                alternative,
                // 빈 칸이면 null 로 보내 서버가 "상계액을 입력해야 합니다"(422)를 돌려주게 한다.
                amount_krw: partial && amount !== '' ? Number(amount) : null,
                opinion,
                actor,
                role,
              }),
            )
          }
        >
          영업 의견 등록
        </button>
        <span className="muted">다시 등록하면 덮어씁니다. 등록 뒤 AI 추천을 다시 받으면 의견이 반영됩니다.</span>
      </div>
    </div>
  )
}

function AiAdvice({ offset }: { offset: OffsetProposal }) {
  if (offset.fallback_used) {
    return (
      <p className="muted">
        <span className="badge badge-neutral">대체 모드</span> AI 추천 없이 상계 한도와 연체
        채권만 남겼습니다. 직접 판단하세요.
      </p>
    )
  }
  return (
    <div>
      <dl className="facts">
        <dt>추천 상계액</dt>
        <dd>
          <strong>
            {offset.ai_amount_krw === null ? '—' : formatKrw(offset.ai_amount_krw)}
          </strong>
          {offset.ai_amount_krw === 0 && ' (상계하지 않고 전액 지급)'}
        </dd>
        <dt>확신도</dt>
        <dd>
          {offset.ai_confidence === null ? '—' : `${Math.round(offset.ai_confidence * 100)}%`}
        </dd>
        <dt>모델</dt>
        <dd>{offset.model ?? '—'}</dd>
      </dl>
      <ListBlock title="근거" items={offset.ai_rationale} />
      <ListBlock title="반대 근거" items={offset.ai_counter_evidence} />
    </div>
  )
}

function ListBlock({ title, items }: { title: string; items: string[] }): ReactNode {
  if (items.length === 0) {
    return null
  }
  return (
    <>
      <h4>{title}</h4>
      <ul>
        {items.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </>
  )
}

function FinanceForm({ offset, busy, run }: RunProps & { offset: OffsetProposal }) {
  const { role, actor } = useRole()
  // 처음 값: AI 추천(0원이면 상계하지 않음 쪽이라 쓰지 않음) → 영업이 권한 부분 상계액 → 상계 한도.
  // 한도 안인지는 서버가 검사한다(422).
  const [amount, setAmount] = useState(
    String(offset.ai_amount_krw || offset.sales_amount_krw || offset.max_offset_krw),
  )
  const [reason, setReason] = useState('')
  const [dueDate, setDueDate] = useState('')

  function decide(decision: Decision, withPlan = false) {
    run(() =>
      decideOffset(offset.offset_id, {
        decision,
        offset_amount_krw: decision === Decision.APPROVE ? Number(amount) : null,
        reason,
        actor,
        role,
        collection_due_date: withPlan && dueDate !== '' ? dueDate : null,
      }),
    )
  }

  return (
    <div className="decision-form">
      <h4>
        재무 결정 <span className="muted">— 지금 역할: {role} · {actor}</span>
      </h4>
      <label>
        상계액(원, 한도 {formatKrw(offset.max_offset_krw)})
        <input
          type="number"
          min={1}
          max={offset.max_offset_krw}
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
        />
      </label>
      <label>
        사유(상계하지 않거나 AI 추천과 다르면 필수)
        <textarea value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      <label>
        회수 약정 기한(지급 + 회수 약정일 때){' '}
        <input type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} />
      </label>
      <div className="actions">
        <button type="button" disabled={busy} onClick={() => decide(Decision.APPROVE)}>
          상계 승인 · 대리점 동의 요청
        </button>
        <button
          type="button"
          disabled={busy || dueDate === ''}
          onClick={() => decide(Decision.REJECT, true)}
        >
          지급 + 회수 약정
        </button>
        <button
          type="button"
          className="danger"
          disabled={busy}
          onClick={() => decide(Decision.REJECT)}
        >
          상계하지 않음(전액 지급)
        </button>
      </div>
    </div>
  )
}

function FinanceView({ offset }: { offset: OffsetProposal }) {
  if (offset.finance_decision === null) {
    return null
  }
  return (
    <p className="muted">
      재무 결정 <strong>{offset.finance_decision}</strong>
      {offset.offset_amount_krw !== null && ` ${formatKrw(offset.offset_amount_krw)}`} (
      {offset.decided_by}
      {offset.decided_at !== null && ` · ${formatDateTime(offset.decided_at)}`})
      {offset.finance_reason !== null && ` — ${offset.finance_reason}`}
      {offset.collection_due_date !== null && ` · 회수 약정 기한 ${offset.collection_due_date}`}
      {offset.agreed !== null && ` · AI 추천과 ${offset.agreed ? '일치' : '불일치'}`}
      {offset.sales_followed !== null &&
        ` · 영업 의견${offset.sales_followed ? '대로' : '과 다르게'} 결정`}
    </p>
  )
}

function ConsentButtons({ offsetId, busy, run }: RunProps & { offsetId: number }) {
  return (
    <div className="decision-form">
      <p className="muted">
        <ProvenanceBadge provenance="모의" /> 대리점의 상계 동의 회신을 시연으로 넣습니다. 실제
        업무에서는 대리점이 보내는 회신입니다.
      </p>
      <div className="actions">
        {[AgencyConsent.CONSENT, AgencyConsent.REFUSE].map((consent) => (
          <button
            key={consent}
            type="button"
            disabled={busy}
            onClick={() => run(() => sendAgencyConsent(offsetId, consent))}
          >
            대리점 {consent}
          </button>
        ))}
      </div>
    </div>
  )
}
