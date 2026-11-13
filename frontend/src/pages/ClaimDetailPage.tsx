/**
 * 장려금 건 상세 페이지.
 * 다음 행동, 원본 기록, 결재 경로(코드 계산)와 관련자 근거, 승인 요청, 지급, 이력을 보여 준다.
 * 서버가 준 값만 보여 주고 판정을 다시 계산하지 않는다. AI 추천 패널은 17 에서 더한다.
 * 행동 버튼은 건 상태만 보고 고른다. 역할 권한은 서버가 403 · 409 로 판단한다(14 결정).
 */
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { decideApproval } from '../api/approvals.ts'
import { ApiError } from '../api/client.ts'
import { decideClaim, getClaim, orderPayment } from '../api/claims.ts'
import { sendBankReply } from '../api/payments.ts'
import AuthorityNotice from '../components/AuthorityNotice.tsx'
import DecisionForm from '../components/DecisionForm.tsx'
import EventTimeline from '../components/EventTimeline.tsx'
import EvidenceTable from '../components/EvidenceTable.tsx'
import ProvenanceBadge from '../components/ProvenanceBadge.tsx'
import StatusBadge from '../components/StatusBadge.tsx'
import { useRole } from '../context/RoleContext.tsx'
import { BankResult, ClaimStatus, PaymentStatus } from '../types/enums.ts'
import type { ClaimDetail } from '../types/rebate.ts'
import { formatDateTime, formatKrw } from '../utils/format.ts'

export default function ClaimDetailPage() {
  const { rebateId } = useParams()
  if (rebateId === undefined) {
    return <p className="error">건 ID 가 없습니다.</p>
  }
  // 구성 건 링크로 다른 건에 가도 같은 페이지라 그대로 남는다.
  // key 가 바뀌면 새로 만들어, 새 건이 오기 전에 이전 건이 보이지 않는다.
  return <ClaimDetailView key={rebateId} rebateId={rebateId} />
}

function ClaimDetailView({ rebateId }: { rebateId: string }) {
  const [detail, setDetail] = useState<ClaimDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  // 행동이 성공하면 이 숫자를 올려 상세를 서버에서 다시 읽는다(화면이 상태를 짐작해 고치지 않음).
  const [reloadKey, setReloadKey] = useState(0)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false
    getClaim(rebateId)
      .then((data) => {
        if (ignore) return
        setDetail(data)
        setError(null)
      })
      .catch((e: unknown) => {
        if (ignore) return
        setError(e instanceof ApiError ? e.message : `요청을 보내지 못했습니다: ${String(e)}`)
      })
    return () => {
      ignore = true
    }
  }, [rebateId, reloadKey])

  /** 행동 하나를 보내고, 성공하면 다시 읽고, 실패하면 서버 문장을 남긴다. 실패해도 버튼은 다시 눌린다. */
  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setActionError(null)
    try {
      await action()
      setReloadKey((key) => key + 1)
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : `요청을 보내지 못했습니다: ${String(e)}`)
    } finally {
      setBusy(false)
    }
  }

  if (detail === null) {
    return error === null ? <p>불러오는 중…</p> : <p className="error">{error}</p>
  }

  return (
    <section>
      <p>
        <Link to="/">← 처리함</Link>
      </p>
      <h2>
        {detail.rebate_id} · {detail.agency_id} {detail.agency_name}{' '}
        <StatusBadge status={detail.status} />
      </h2>
      {error !== null && <p className="error">{error}</p>}

      <NextAction detail={detail} busy={busy} error={actionError} run={run} />

      <section className="detail-section">
        <h3>
          원본 기록 <ProvenanceBadge provenance="원본" />
        </h3>
        <dl className="facts">
          <dt>대상월</dt>
          <dd>{detail.period_ym}</dd>
          <dt>판매 실적</dt>
          <dd>{formatKrw(detail.sales_performance_krw)}</dd>
          <dt>장려금액</dt>
          <dd>{formatKrw(detail.rebate_amount_krw)}</dd>
          <dt>원본 상태</dt>
          <dd>{detail.original_status}</dd>
          <dt>원본 결재자</dt>
          <dd>{detail.original_approver ?? '없음'}</dd>
          <dt>원본 지급일</dt>
          <dd>{detail.original_payment_date ?? '없음'}</dd>
          <dt>출처</dt>
          <dd>
            {detail.source_file}:{detail.source_row}
          </dd>
        </dl>
      </section>

      <section className="detail-section">
        <h3>결재 경로(코드 계산)</h3>
        <AuthorityNotice
          minAuthority={detail.min_authority}
          groupLabel={detail.group_label}
          groupSum={detail.group_sum_krw}
          limit={detail.limit_krw}
        />
        {detail.unit_claims.length > 0 && (
          <div className="table-scroll">
            <table className="claim-table">
              <thead>
                <tr>
                  <th>판정 단위 구성 건</th>
                  <th>대리점</th>
                  <th>장려금액</th>
                  <th>상태</th>
                </tr>
              </thead>
              <tbody>
                {detail.unit_claims.map((c) => (
                  <tr
                    key={c.rebate_id}
                    className={c.rebate_id === detail.rebate_id ? 'current-row' : undefined}
                  >
                    <td>
                      <Link to={`/claims/${c.rebate_id}`}>{c.rebate_id}</Link>
                    </td>
                    <td>
                      {c.agency_id} · {c.agency_name}
                    </td>
                    <td className="num">{formatKrw(c.rebate_amount_krw)}</td>
                    <td>
                      <StatusBadge status={c.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="detail-section">
        <h3>관련자 근거</h3>
        <EvidenceTable edges={detail.evidence} />
      </section>

      {detail.approval !== null && (
        <section className="detail-section">
          <h3>승인 요청 #{detail.approval.request_id}</h3>
          <dl className="facts">
            <dt>요구 결재권자</dt>
            <dd>{detail.approval.approver_role}</dd>
            <dt>판정 단위 합산</dt>
            <dd>{formatKrw(detail.approval.group_sum_krw)}</dd>
            <dt>포함 건</dt>
            <dd>{detail.approval.rebate_ids.join(', ')}</dd>
            <dt>결정</dt>
            <dd>
              {detail.approval.decision === null ? (
                '결정 전'
              ) : (
                <>
                  {detail.approval.decision} · {detail.approval.decided_by}
                  {detail.approval.decided_at !== null &&
                    ` · ${formatDateTime(detail.approval.decided_at)}`}
                </>
              )}
            </dd>
            {detail.approval.reason !== null && (
              <>
                <dt>사유</dt>
                <dd>{detail.approval.reason}</dd>
              </>
            )}
          </dl>
        </section>
      )}

      <section className="detail-section">
        <h3>지급</h3>
        {detail.payments.length === 0 ? (
          <p className="muted">지급 지시 없음</p>
        ) : (
          <div className="table-scroll">
            <table className="claim-table">
              <thead>
                <tr>
                  <th>지시 번호</th>
                  <th>금액</th>
                  <th>지시자</th>
                  <th>지시 시각</th>
                  <th>지시 상태</th>
                  <th>은행 회신</th>
                </tr>
              </thead>
              <tbody>
                {detail.payments.map((p) => (
                  <tr key={p.payment_id}>
                    <td>{p.payment_id}</td>
                    <td className="num">{formatKrw(p.amount_krw)}</td>
                    <td>{p.ordered_by}</td>
                    <td>{formatDateTime(p.ordered_at)}</td>
                    <td>{p.status}</td>
                    <td>
                      {p.bank_result === null ? (
                        '—'
                      ) : (
                        <>
                          {p.bank_result}{' '}
                          {p.bank_provenance !== null && (
                            <ProvenanceBadge provenance={p.bank_provenance} />
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="detail-section">
        <h3>이력</h3>
        <EventTimeline events={detail.events} />
      </section>
    </section>
  )
}

type NextActionProps = {
  detail: ClaimDetail
  busy: boolean
  error: string | null
  run: (action: () => Promise<unknown>) => void
}

/** 지금 상태에서 할 수 있는 행동. 누가 할 수 있는지는 서버가 판단한다. */
function NextAction({ detail, busy, error, run }: NextActionProps) {
  const { role, actor } = useRole()
  const { approval } = detail
  const lastPayment = detail.payments.at(-1)

  let title: string
  let body: ReactNode
  if (detail.status === ClaimStatus.AWAITING_SUPPORT) {
    title = '전결 결정'
    body = (
      <DecisionForm
        busy={busy}
        onDecide={(decision, reason) =>
          run(() => decideClaim(detail.rebate_id, { decision, reason, actor, role }))
        }
      />
    )
  } else if (
    detail.status === ClaimStatus.AWAITING_EXECUTIVE &&
    approval !== null &&
    approval.decision === null
  ) {
    title = `승인 요청 #${approval.request_id} 결정`
    body = (
      <>
        <p>
          포함 {approval.rebate_ids.length}건({approval.rebate_ids.join(', ')})이 함께 바뀝니다.
        </p>
        <DecisionForm
          busy={busy}
          onDecide={(decision, reason) =>
            run(() => decideApproval(approval.request_id, { decision, reason, actor, role }))
          }
        />
      </>
    )
  } else if (detail.status === ClaimStatus.APPROVED || detail.status === ClaimStatus.ON_HOLD) {
    title = '지급 지시'
    body = (
      <div className="actions">
        <button
          type="button"
          disabled={busy}
          onClick={() => run(() => orderPayment(detail.rebate_id, actor, role))}
        >
          지급 지시
        </button>
      </div>
    )
  } else if (
    detail.status === ClaimStatus.PAYMENT_ORDERED &&
    lastPayment !== undefined &&
    lastPayment.status === PaymentStatus.AWAITING_REPLY
  ) {
    title = '은행 회신'
    body = (
      <>
        <p className="muted">
          <ProvenanceBadge provenance="모의" /> 외부(은행) 사건을 시연으로 넣습니다. 실제
          업무에서는 은행이 보내는 회신입니다.
        </p>
        <div className="actions">
          {[BankResult.SUCCESS, BankResult.ACCOUNT_ERROR].map((result) => (
            <button
              key={result}
              type="button"
              disabled={busy}
              onClick={() => run(() => sendBankReply(lastPayment.payment_id, result))}
            >
              {result}
            </button>
          ))}
        </div>
      </>
    )
  } else {
    return null
  }

  return (
    <section className="detail-section next-action">
      <h3>
        {title} <span className="muted">— 지금 역할: {role} · {actor}</span>
      </h3>
      {body}
      {error !== null && <p className="error">{error}</p>}
    </section>
  )
}
