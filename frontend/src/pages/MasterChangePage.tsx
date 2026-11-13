/**
 * 마스터 정정 신고 페이지.
 * 대리점이 신고한 대표자 · 주소 · 등록계좌 정정을 적용하고, 관련자 그룹이 어떻게 바뀌었는지(또는 유지되었는지),
 * 그 근거 행, 다시 판정된 건을 보여 준다. 서버가 돌려준 값을 그대로 보여 주고 판정을 다시 계산하지 않는다.
 * 신고 문장을 AI 가 해석하는 master_change_parser(19)는 이 폼의 앞단이 된다.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { applyMasterChange, listMasterChanges } from '../api/agencies.ts'
import { ApiError } from '../api/client.ts'
import EvidenceTable from '../components/EvidenceTable.tsx'
import ProvenanceBadge from '../components/ProvenanceBadge.tsx'
import StatusBadge from '../components/StatusBadge.tsx'
import { useRole } from '../context/RoleContext.tsx'
import {
  CORRECTABLE_ATTRS,
  type CorrectableAttr,
  type GroupItem,
  type MasterChangeItem,
  type MasterChangeResult,
} from '../types/masterChange.ts'
import { formatDateTime, formatKrw } from '../utils/format.ts'

/** 시나리오 2 의 시연 신고 두 건. 입력칸에 채워 넣는다. */
const DEMOS = [
  {
    label: 'D-037 정산계좌 변경(그룹 유지)',
    agencyId: 'D-037',
    attrType: '등록계좌' as CorrectableAttr,
    newValue: '신한 123-45-678901',
    reportedText: '정산 계좌를 신한은행으로 옮겼습니다.',
  },
  {
    label: 'D-041 주소 정정(새 그룹)',
    agencyId: 'D-041',
    attrType: '주소' as CorrectableAttr,
    newValue: '대전시 중앙로 260',
    reportedText: '본사를 대전시 중앙로 260 으로 이전했습니다.',
  },
]

export default function MasterChangePage() {
  const { role, actor } = useRole()
  const [agencyId, setAgencyId] = useState('')
  const [attrType, setAttrType] = useState<CorrectableAttr>('주소')
  const [newValue, setNewValue] = useState('')
  const [effectiveDate, setEffectiveDate] = useState('')
  const [reportedText, setReportedText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<MasterChangeResult | null>(null)
  const [history, setHistory] = useState<MasterChangeItem[]>([])
  // 적용이 성공하면 이 숫자를 올려 이력을 서버에서 다시 읽는다.
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let ignore = false
    listMasterChanges()
      .then((items) => {
        if (!ignore) setHistory(items)
      })
      .catch(() => {
        // 이력은 보조 정보라 실패해도 신고 폼은 쓸 수 있다.
      })
    return () => {
      ignore = true
    }
  }, [reloadKey])

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const applied = await applyMasterChange(agencyId.trim(), {
        attr_type: attrType,
        new_value: newValue,
        effective_date: effectiveDate === '' ? null : effectiveDate,
        reported_text: reportedText,
        actor,
        role,
      })
      setResult(applied)
      setReloadKey((key) => key + 1)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `요청을 보내지 못했습니다: ${String(e)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <h2>마스터 정정 신고</h2>
      <p className="muted">
        <ProvenanceBadge provenance="주장" /> 대리점이 신고한 값입니다. 적용하면 원본 마스터는 그대로 두고
        유효기간만 닫은 뒤 관련자 그룹을 새 버전으로 다시 계산합니다. 지금 역할: {role} · {actor}
      </p>

      <div className="decision-form">
        <div className="actions">
          {DEMOS.map((demo) => (
            <button
              key={demo.label}
              type="button"
              disabled={busy}
              onClick={() => {
                setAgencyId(demo.agencyId)
                setAttrType(demo.attrType)
                setNewValue(demo.newValue)
                setReportedText(demo.reportedText)
              }}
            >
              {demo.label} 채우기
            </button>
          ))}
        </div>
        <div className="toolbar">
          <label>
            대리점 ID{' '}
            <input value={agencyId} onChange={(event) => setAgencyId(event.target.value)} placeholder="D-037" />
          </label>
          <label>
            속성{' '}
            <select value={attrType} onChange={(event) => setAttrType(event.target.value as CorrectableAttr)}>
              {CORRECTABLE_ATTRS.map((attr) => (
                <option key={attr} value={attr}>
                  {attr}
                </option>
              ))}
            </select>
          </label>
          <label>
            새 값 <input value={newValue} onChange={(event) => setNewValue(event.target.value)} />
          </label>
          <label>
            정정일(비우면 오늘){' '}
            <input type="date" value={effectiveDate} onChange={(event) => setEffectiveDate(event.target.value)} />
          </label>
        </div>
        <label>
          신고 원문(선택)
          <textarea value={reportedText} onChange={(event) => setReportedText(event.target.value)} />
        </label>
        <div className="actions">
          <button type="button" disabled={busy} onClick={submit}>
            정정 적용
          </button>
        </div>
        {error !== null && <p className="error">{error}</p>}
      </div>

      {result !== null && <ResultView result={result} />}

      <section className="detail-section">
        <h3>정정 신고 이력</h3>
        {history.length === 0 ? (
          <p className="muted">신고 없음</p>
        ) : (
          <div className="table-scroll">
            <table className="claim-table">
              <thead>
                <tr>
                  <th>번호</th>
                  <th>대리점</th>
                  <th>속성</th>
                  <th>이전 값</th>
                  <th>새 값</th>
                  <th>정정일</th>
                  <th>적용</th>
                </tr>
              </thead>
              <tbody>
                {history.map((item) => (
                  <tr key={item.change_id}>
                    <td>{item.change_id}</td>
                    <td>{item.agency_id}</td>
                    <td>{item.attr_type}</td>
                    <td>{item.old_value}</td>
                    <td>{item.new_value}</td>
                    <td>{item.effective_date}</td>
                    <td>
                      {item.reported_by} · {formatDateTime(item.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </section>
  )
}

function GroupLine({ groups }: { groups: GroupItem[] }) {
  if (groups.length === 0) {
    return <>그룹 없음</>
  }
  return <>{groups.map((g) => `${g.label}: ${g.members.join(', ')}`).join(' / ')}</>
}

function ResultView({ result }: { result: MasterChangeResult }) {
  const { change } = result
  return (
    <section className="detail-section next-action">
      <h3>
        정정 #{change.change_id} 적용 — {change.agency_id} {change.attr_type}{' '}
        <span className={`badge badge-${result.group_retained ? 'ok' : 'stop'}`}>
          {result.group_retained ? '그룹 유지(결론 유지)' : '그룹 변경'}
        </span>
      </h3>
      <dl className="facts">
        <dt>값</dt>
        <dd>
          {change.old_value} → <strong>{change.new_value}</strong> (정정일 {change.effective_date})
        </dd>
        <dt>그룹 버전</dt>
        <dd>
          v{result.version_no_before} → v{result.version_no_after}
        </dd>
        <dt>정정 전</dt>
        <dd>
          <GroupLine groups={result.groups_before} />
        </dd>
        <dt>정정 후</dt>
        <dd>
          <GroupLine groups={result.groups_after} />
        </dd>
        {result.affected_agencies.length > 0 && (
          <>
            <dt>소속이 바뀐 대리점</dt>
            <dd>{result.affected_agencies.join(', ')}</dd>
          </>
        )}
      </dl>

      <h4>{change.agency_id} 가 낀 관련자 근거(새 버전)</h4>
      <p className="muted">
        근거 행의 <code>master_change:번호</code> 는 이번 신고 값이라 <ProvenanceBadge provenance="주장" /> 이고,
        파일 이름 행은 <ProvenanceBadge provenance="원본" /> 입니다.
      </p>
      <EvidenceTable edges={result.evidence} />

      <h4>다시 판정된 건</h4>
      {result.claims.length === 0 ? (
        <p className="muted">
          {result.group_retained
            ? '그룹이 그대로라 다시 판정할 건이 없습니다.'
            : '소속이 바뀐 대리점에 아직 돈이 나가지 않은 건이 없습니다.'}
        </p>
      ) : (
        <div className="table-scroll">
          <table className="claim-table">
            <thead>
              <tr>
                <th>건</th>
                <th>대리점</th>
                <th>대상월</th>
                <th>상태 변화</th>
                <th>최소 결재권자</th>
                <th>판정 단위 합산</th>
                <th>승인 요청</th>
              </tr>
            </thead>
            <tbody>
              {result.claims.map((claim) => (
                <tr key={claim.rebate_id}>
                  <td>
                    <Link to={`/claims/${claim.rebate_id}`}>{claim.rebate_id}</Link>
                  </td>
                  <td>{claim.agency_id}</td>
                  <td>{claim.period_ym}</td>
                  <td>
                    <StatusBadge status={claim.from_status} /> → <StatusBadge status={claim.to_status} />
                  </td>
                  <td>
                    {claim.min_authority_before ?? '—'} →{' '}
                    {claim.min_authority_after ?? '재판정 전'}
                  </td>
                  <td className="num">
                    {claim.group_sum_before === null ? '—' : formatKrw(claim.group_sum_before)} →{' '}
                    {claim.group_sum_after === null ? '재판정 전' : formatKrw(claim.group_sum_after)}
                  </td>
                  <td>{claim.approval_request_id === null ? '—' : `#${claim.approval_request_id}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
