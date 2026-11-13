/**
 * 관련자 근거 표.
 * 일치한 대리점 쌍마다 속성 · 값 · 양쪽 원본 행을 한 줄씩 나열한다.
 */
import type { RelationEdge } from '../types/relatedParty.ts'
import ProvenanceBadge from './ProvenanceBadge.tsx'

export default function EvidenceTable({ edges }: { edges: RelationEdge[] }) {
  if (edges.length === 0) {
    return <p className="muted">일치하는 다른 대리점이 없습니다(단독).</p>
  }
  return (
    <div className="table-scroll">
      <table className="claim-table">
        <thead>
          <tr>
            <th>대리점 쌍</th>
            <th>판정</th>
            <th>속성</th>
            <th>값</th>
            <th>
              A 근거 행 <ProvenanceBadge provenance="원본" />
            </th>
            <th>
              B 근거 행 <ProvenanceBadge provenance="원본" />
            </th>
          </tr>
        </thead>
        <tbody>
          {edges.flatMap((edge) =>
            edge.matched_attrs.map((m) => (
              <tr key={`${edge.agency_a}-${edge.agency_b}-${m.attr}-${m.value}`}>
                <td>
                  {edge.agency_a} – {edge.agency_b}
                </td>
                <td>
                  {edge.judgement}({edge.match_count}개 일치)
                </td>
                <td>{m.attr}</td>
                <td>{m.value}</td>
                <td>{m.refs_a.join(', ')}</td>
                <td>{m.refs_b.join(', ')}</td>
              </tr>
            )),
          )}
        </tbody>
      </table>
    </div>
  )
}
