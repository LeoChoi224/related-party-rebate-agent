/**
 * 데이터 출처 배지: [원본] [주장] [가정] [모의].
 */
import type { Provenance } from '../types/enums.ts'

export default function ProvenanceBadge({ provenance }: { provenance: Provenance }) {
  return <span className="badge badge-prov">[{provenance}]</span>
}
