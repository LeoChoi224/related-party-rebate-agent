/**
 * 결재권자 안내.
 * 코드가 계산한 판정 단위 합산 · 한도 · 최소 결재권자를 나란히 보여 준다.
 * AI 가 낮게 판단해 코드가 올린 경우의 표시는 AI 추천을 붙이는 17 에서 더한다.
 */
import { formatKrw } from '../utils/format.ts'

type Props = {
  minAuthority: string | null
  groupLabel: string | null
  groupSum: number | null
  limit: number
}

export default function AuthorityNotice({ minAuthority, groupLabel, groupSum, limit }: Props) {
  if (minAuthority === null || groupSum === null) {
    return <p className="muted">아직 한도 판정 전입니다(대상월 접수 때 판정합니다).</p>
  }
  // 합산과 한도를 화면에서 비교하지 않는다. 판정 규칙은 서버(06) 한 곳에만 둔다.
  return (
    <p>
      판정 단위 {groupLabel ?? '단독'} 합산 <strong>{formatKrw(groupSum)}</strong> · 한도{' '}
      {formatKrw(limit)} → 최소 결재권자 <strong>{minAuthority}</strong>
    </p>
  )
}
