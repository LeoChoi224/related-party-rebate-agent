/**
 * 결정 폼: 사유 입력과 승인 · 반려 버튼.
 * 반려할 때 소명 요청 항목을 적으면 반려와 함께 대리점에 소명을 요청한다(21).
 * 반려 사유가 비었는지는 서버가 검사해 422 문장을 돌려준다(화면에 같은 규칙을 두지 않는다).
 * AI 추천과 다르게 고르면 사유 필수는 25 에서 더한다.
 */
import { useState } from 'react'
import { Decision } from '../types/enums.ts'

type Props = {
  busy: boolean
  onDecide: (decision: Decision, reason: string, explanationItems: string[]) => void
}

export default function DecisionForm({ busy, onDecide }: Props) {
  const [reason, setReason] = useState('')
  const [items, setItems] = useState('')

  return (
    <div className="decision-form">
      <label>
        사유(반려는 필수)
        <textarea value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      <label>
        소명 요청 항목(반려할 때만, 한 줄에 하나 — 비우면 소명 요청 없이 반려)
        <textarea value={items} onChange={(event) => setItems(event.target.value)} />
      </label>
      <div className="actions">
        <button type="button" disabled={busy} onClick={() => onDecide(Decision.APPROVE, reason, [])}>
          승인
        </button>
        <button
          type="button"
          className="danger"
          disabled={busy}
          onClick={() =>
            onDecide(
              Decision.REJECT,
              reason,
              items.split('\n').filter((line) => line.trim() !== ''),
            )
          }
        >
          반려
        </button>
      </div>
    </div>
  )
}
