/**
 * 소명 API: 소명 요청, 회신 등록 [모의], AI 검토, 영업지원팀 확인.
 */
import type {
  Explanation,
  ExplanationConfirmBody,
  ExplanationConfirmResult,
} from '../types/explanation.ts'
import { api } from './client.ts'

/** 반려 · 지급보류 건에 소명을 요청한다. 권한 403, 다른 상태 · 진행 중인 요청 409, 빈 항목 422. */
export function requestExplanation(
  rebateId: string,
  requestedItems: string[],
  actor: string,
  role: string,
): Promise<Explanation> {
  return api.post<Explanation>(`/claims/${encodeURIComponent(rebateId)}/explanation-requests`, {
    requested_items: requestedItems,
    actor,
    role,
  })
}

/** 대리점 회신 [모의] 을 등록한다. 요청 하나에 한 번만(409). */
export function sendExplanationReply(expId: number, rawText: string): Promise<Explanation> {
  return api.post<Explanation>(`/explanation-requests/${expId}/reply`, { raw_text: rawText })
}

/** AI 검토를 사람 확인 앞까지 돌린다. LLM 을 여러 번 부르므로 몇 초 걸릴 수 있다. */
export function reviewExplanation(replyId: number): Promise<Explanation> {
  return api.post<Explanation>(`/explanations/${replyId}/review`)
}

/** 영업지원팀이 소명을 확인한다. 권한 403, 이미 확인 409, 사유 없는 증빙 부족 422. */
export function confirmExplanation(
  replyId: number,
  body: ExplanationConfirmBody,
): Promise<ExplanationConfirmResult> {
  return api.post<ExplanationConfirmResult>(`/explanations/${replyId}/decision`, body)
}
