/**
 * AI 추천 패널.
 * AI 출력은 사실이 아니라 주장이라 [주장] 으로 표시한다. 결재권자는 코드 값(min_authority)이다.
 * 서버가 저장한 가드 결과(올림 · 대체 모드)를 그대로 보여 주고 화면은 다시 판단하지 않는다.
 */
import type { AiReview } from '../types/aiReview.ts'
import { formatDateTime } from '../utils/format.ts'
import ProvenanceBadge from './ProvenanceBadge.tsx'

export default function AiPanel({ review }: { review: AiReview }) {
  return (
    <div>
      {review.fallback_used ? (
        <p className="muted">
          <span className="badge badge-neutral">대체 모드</span> AI 추천 없이 규정 결과만
          남겼습니다. 최소 결재권자 <strong>{review.min_authority}</strong> 기준으로 직접
          판단하세요.
        </p>
      ) : (
        <>
          <dl className="facts">
            <dt>추천</dt>
            <dd>
              <strong>{review.recommendation}</strong>{' '}
              <ProvenanceBadge provenance="주장" />
            </dd>
            <dt>확신도</dt>
            <dd>{review.confidence === null ? '—' : `${Math.round(review.confidence * 100)}%`}</dd>
            <dt>결재권자</dt>
            <dd>
              AI {review.ai_authority} · 코드 <strong>{review.min_authority}</strong>
            </dd>
            <dt>모델</dt>
            <dd>{review.model ?? '—'}</dd>
          </dl>
          {review.authority_raised && (
            <p className="error">
              AI 는 {review.ai_authority} 결재로 봤지만, 규정상 최소 결재권자는{' '}
              {review.min_authority} 입니다. 코드가 결재 단계를 올려 고정했습니다(AI 는 올릴 수만
              있습니다).
            </p>
          )}
          <h4>근거</h4>
          <ul>
            {review.rationale.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <h4>반대 근거 · 확인할 점</h4>
          {review.counter_evidence.length === 0 ? (
            <p className="muted">없음</p>
          ) : (
            <ul>
              {review.counter_evidence.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}
        </>
      )}
      <p className="muted">
        검토 {formatDateTime(review.created_at)}
        {review.human_decision !== null && (
          <>
            {' '}
            · 사람 결정 <strong>{review.human_decision}</strong> ({review.decided_by})
            {review.agreed !== null && ` · AI 추천과 ${review.agreed ? '일치' : '불일치'}`}
          </>
        )}
      </p>
    </div>
  )
}
