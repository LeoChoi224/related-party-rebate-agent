/**
 * 결정 폼: 사유 입력과 승인 · 반려 버튼.
 * 반려할 때 소명 요청 항목을 적으면 반려와 함께 대리점에 소명을 요청한다(21).
 * 반려 사유가 비었는지, AI 추천과 다르게 골랐는데 사유가 없는지(25)는 서버가 검사해 422 문장을 돌려준다
 * (화면에 같은 규칙을 두지 않고, 기다리는 AI 추천을 안내만 한다).
 */
import { useState } from 'react'
import { Decision } from '../types/enums.ts'

type Props = {
  busy: boolean
  /** 결정을 기다리는 AI 추천(대체 모드 · 추천 전이면 null). 안내 문장에만 쓴다. */
  aiRecommendation?: string | null
  onDecide: (decision: Decision, reason: string, explanationItems: string[]) => void
}

export default function DecisionForm({ busy, aiRecommendation = null, onDecide }: Props) {
  const [reason, setReason] = useState('')
  const [items, setItems] = useState('')

  return (
    <div className="decision-form">
      {aiRecommendation !== null && (
        <p className="muted">
          AI 추천은 <strong>{aiRecommendation}</strong> 입니다("소명 먼저"는 반려 + 소명 요청). 다르게
          결정하면 사유를 입력해야 합니다.
        </p>
      )}
      <label>
        사유(반려 · AI 추천과 다른 결정은 필수)
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
