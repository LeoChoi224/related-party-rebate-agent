/**
 * 건 상세의 소명 칸: 소명 요청 · 대리점 회신 [모의] · AI 주장별 대조 결과 [주장] · 영업지원팀 확인.
 * 서버가 저장한 값을 그대로 보여 주고 판정을 다시 계산하지 않는다.
 * 버튼은 건 상태 · 요청 상태만 보고 보인다. 역할 권한은 서버가 403 · 409 로 판단한다(14 결정).
 * 이 칸은 자기 오류 문장과 처리 중 표시를 따로 가진다. 성공하면 onChanged 로 상세를 다시 읽게 한다.
 */
import { useState, type ReactNode } from 'react'
import { ApiError } from '../api/client.ts'
import {
  confirmExplanation,
  requestExplanation,
  reviewExplanation,
  sendExplanationReply,
} from '../api/explanations.ts'
import { useRole } from '../context/RoleContext.tsx'
import {
  CheckVerdict,
  ClaimStatus,
  ExplanationJudgement,
  ExplanationStatus,
} from '../types/enums.ts'
import type { Explanation, ExplanationReply } from '../types/explanation.ts'
import type { ClaimDetail } from '../types/rebate.ts'
import { formatDateTime } from '../utils/format.ts'
import ProvenanceBadge from './ProvenanceBadge.tsx'

/** 시나리오 3 의 모의 회신 문구. 시연할 때 입력칸에 채워 넣는다. */
const DEMO_REPLY = 'D-024는 별도 법인이고, 계좌가 겹친 건 세무대리인이 대신 입금해서입니다.'

const VERDICT_TONE: Record<CheckVerdict, string> = {
  일치: 'ok',
  불일치: 'stop',
  확인불가: 'neutral',
}

const STATUS_TONE: Record<ExplanationStatus, string> = {
  회신대기: 'wait',
  회신됨: 'wait',
  확인완료: 'ok',
  취소: 'neutral',
}

type Props = {
  detail: ClaimDetail
  onChanged: () => void
}

export default function ExplanationSection({ detail, onChanged }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const canRequest =
    detail.status === ClaimStatus.REJECTED || detail.status === ClaimStatus.ON_HOLD
  if (detail.explanations.length === 0 && !canRequest) {
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
      <h3>소명</h3>
      {detail.explanations.map((explanation) => (
        <ExplanationCard
          key={explanation.exp_id}
          explanation={explanation}
          busy={busy}
          run={run}
        />
      ))}
      {canRequest && <RequestForm rebateId={detail.rebate_id} busy={busy} run={run} />}
      {error !== null && <p className="error">{error}</p>}
    </section>
  )
}

type RunProps = {
  busy: boolean
  run: (action: () => Promise<unknown>) => void
}

function RequestForm({ rebateId, busy, run }: RunProps & { rebateId: string }) {
  const { role, actor } = useRole()
  const [items, setItems] = useState('')

  return (
    <div className="decision-form">
      <label>
        소명 요청 항목(한 줄에 하나)
        <textarea value={items} onChange={(event) => setItems(event.target.value)} />
      </label>
      <div className="actions">
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            run(() =>
              requestExplanation(
                rebateId,
                items.split('\n').filter((line) => line.trim() !== ''),
                actor,
                role,
              ),
            )
          }
        >
          소명 요청
        </button>
      </div>
    </div>
  )
}

function ExplanationCard({
  explanation,
  busy,
  run,
}: RunProps & { explanation: Explanation }) {
  const { reply } = explanation
  return (
    <div className="next-action">
      <h4>
        소명 요청 #{explanation.exp_id}{' '}
        <span className={`badge badge-${STATUS_TONE[explanation.status]}`}>
          {explanation.status}
        </span>
      </h4>
      <dl className="facts">
        <dt>요청 항목</dt>
        <dd>{explanation.requested_items.join(' / ')}</dd>
        <dt>요청</dt>
        <dd>
          {explanation.requested_by} · {formatDateTime(explanation.created_at)}
        </dd>
      </dl>
      {reply === null ? (
        <ReplyForm expId={explanation.exp_id} busy={busy} run={run} />
      ) : (
        <ReplyView explanation={explanation} reply={reply} busy={busy} run={run} />
      )}
    </div>
  )
}

function ReplyForm({ expId, busy, run }: RunProps & { expId: number }) {
  const [text, setText] = useState('')
  return (
    <div className="decision-form">
      <p className="muted">
        <ProvenanceBadge provenance="모의" /> 대리점 회신을 시연으로 넣습니다. 실제 업무에서는
        대리점이 보내는 회신입니다. 등록하면 AI 검토(주장 대조)가 바로 돌아 몇 초 걸릴 수 있습니다.
      </p>
      <label>
        회신 내용
        <textarea value={text} onChange={(event) => setText(event.target.value)} />
      </label>
      <div className="actions">
        <button type="button" disabled={busy} onClick={() => setText(DEMO_REPLY)}>
          시연 문구 채우기
        </button>
        <button type="button" disabled={busy} onClick={() => run(() => sendExplanationReply(expId, text))}>
          회신 등록
        </button>
      </div>
    </div>
  )
}

function ReplyView({
  explanation,
  reply,
  busy,
  run,
}: RunProps & { explanation: Explanation; reply: ExplanationReply }) {
  const reviewed = reply.verified || reply.fallback_used
  return (
    <>
      <h4>
        회신 <ProvenanceBadge provenance={reply.provenance} />
      </h4>
      <p>{reply.raw_text}</p>

      <h4>
        AI 검토 <ProvenanceBadge provenance="주장" />
      </h4>
      {reviewed ? (
        <AiResult reply={reply} />
      ) : explanation.status === ExplanationStatus.REPLIED ? (
        <div className="actions">
          <button type="button" disabled={busy} onClick={() => run(() => reviewExplanation(reply.reply_id))}>
            AI 검토
          </button>
          <span className="muted">LLM 을 여러 번 부르므로 몇 초 걸릴 수 있습니다.</span>
        </div>
      ) : (
        <p className="muted">AI 검토 기록 없음</p>
      )}

      {explanation.status === ExplanationStatus.REPLIED && (
        <ConfirmForm replyId={reply.reply_id} busy={busy} run={run} />
      )}
      {explanation.status === ExplanationStatus.CONFIRMED && <ConfirmedView reply={reply} />}
    </>
  )
}

function AiResult({ reply }: { reply: ExplanationReply }) {
  return (
    <div>
      {reply.checks.length > 0 && (
        <div className="table-scroll">
          <table className="claim-table">
            <thead>
              <tr>
                <th>주장</th>
                <th>판정</th>
                <th>대조 결과</th>
                <th>근거 행</th>
                <th>조회 도구</th>
              </tr>
            </thead>
            <tbody>
              {reply.checks.map((check) => (
                <tr key={check.check_id}>
                  <td className="wrap">{check.claim_text}</td>
                  <td>
                    <span className={`badge badge-${VERDICT_TONE[check.verdict]}`}>
                      {check.verdict}
                    </span>
                  </td>
                  <td className="wrap">{check.finding}</td>
                  <td>{check.evidence_ref.length === 0 ? '—' : check.evidence_ref.join(', ')}</td>
                  <td>{check.tool_used.length === 0 ? '—' : check.tool_used.join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {reply.fallback_used ? (
        <p className="muted">
          <span className="badge badge-neutral">대체 모드</span> AI 종합 판단 없이 회신 원문과
          위 대조 결과만 남겼습니다. 직접 판단하세요.
        </p>
      ) : (
        <>
          <dl className="facts">
            <dt>AI 판단</dt>
            <dd>
              <strong>{reply.ai_judgement}</strong>
            </dd>
            <dt>확신도</dt>
            <dd>
              {reply.ai_confidence === null ? '—' : `${Math.round(reply.ai_confidence * 100)}%`}
            </dd>
            <dt>모델</dt>
            <dd>{reply.model ?? '—'}</dd>
          </dl>
          <ListBlock title="근거" items={reply.ai_rationale} />
          <ListBlock title="부족한 증빙" items={reply.missing_evidence} />
          {reply.follow_up_request !== null && (
            <>
              <h4>추가 요청문(초안)</h4>
              <p>{reply.follow_up_request}</p>
            </>
          )}
        </>
      )}
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

function ConfirmForm({ replyId, busy, run }: RunProps & { replyId: number }) {
  const { role, actor } = useRole()
  const [reason, setReason] = useState('')

  function confirm(judgement: ExplanationJudgement) {
    run(() => confirmExplanation(replyId, { judgement, reason, actor, role }))
  }

  return (
    <div className="decision-form">
      <h4>
        영업지원팀 확인 <span className="muted">— 지금 역할: {role} · {actor}</span>
      </h4>
      <label>
        사유(증빙 부족은 필수)
        <textarea value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      <div className="actions">
        <button type="button" disabled={busy} onClick={() => confirm(ExplanationJudgement.SUFFICIENT)}>
          증빙 충분
        </button>
        <button
          type="button"
          className="danger"
          disabled={busy}
          onClick={() => confirm(ExplanationJudgement.INSUFFICIENT)}
        >
          증빙 부족
        </button>
      </div>
    </div>
  )
}

function ConfirmedView({ reply }: { reply: ExplanationReply }) {
  return (
    <p className="muted">
      영업지원팀 확인 <strong>{reply.review_result}</strong> ({reply.reviewed_by}
      {reply.reviewed_at !== null && ` · ${formatDateTime(reply.reviewed_at)}`})
      {reply.review_reason !== null && ` — ${reply.review_reason}`}
      {reply.agreed !== null && ` · AI 판단과 ${reply.agreed ? '일치' : '불일치'}`}
    </p>
  )
}
