/**
 * 장려금 건 상태 배지(전결대기, 상신대기, 지급보류 등).
 * 색은 보기용 묶음일 뿐이다. 다음에 누가 처리하는지 같은 업무 규칙은 넣지 않는다.
 */
import type { ClaimStatus } from '../types/enums.ts'

type Tone = 'neutral' | 'wait' | 'ok' | 'stop'

// Record 라서 상태 14개 중 하나라도 빠지면 빌드가 실패한다.
const TONE: Record<ClaimStatus, Tone> = {
  미접수: 'neutral',
  접수: 'neutral',
  관계확인: 'neutral',
  전결대기: 'wait',
  상신대기: 'wait',
  소명대기: 'wait',
  상계검토: 'wait',
  지급지시: 'wait',
  승인: 'ok',
  지급완료: 'ok',
  상계완료: 'ok',
  반려: 'stop',
  지급보류: 'stop',
  재검토필요: 'stop',
}

export default function StatusBadge({ status }: { status: ClaimStatus }) {
  return <span className={`badge badge-${TONE[status]}`}>{status}</span>
}
