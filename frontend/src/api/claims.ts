/**
 * 장려금 건 API: 처리함 목록, 건 상세, 대상월 접수, 전결 결정, 지급 지시, AI 검토, 재판정.
 */
import type { AiReview } from '../types/aiReview.ts'
import type { ClaimDecisionResult, DecisionRequest } from '../types/approval.ts'
import type { ClaimStatus } from '../types/enums.ts'
import type { RejudgeResult } from '../types/masterChange.ts'
import type { PaymentOrderResult } from '../types/payment.ts'
import type { ClaimDetail, ClaimListItem, IntakeResult } from '../types/rebate.ts'
import { api } from './client.ts'

/** 고른 상태의 건 목록(건 ID 순). 빈 배열이면 전체. */
export function listClaims(statuses: readonly ClaimStatus[]): Promise<ClaimListItem[]> {
  const params = new URLSearchParams()
  // set 은 같은 이름을 덮어써 마지막 하나만 남는다. 서버는 ?status=A&status=B 를 받는다.
  for (const status of statuses) {
    params.append('status', status)
  }
  const query = params.toString()
  return api.get<ClaimListItem[]>(query === '' ? '/claims' : `/claims?${query}`)
}

/** 대상월(YYYY-MM)의 장려금 건을 모두 접수해 전결대기 · 상신대기로 보낸다. */
export function intakePeriod(period: string): Promise<IntakeResult> {
  return api.post<IntakeResult>(`/claims/intake?${new URLSearchParams({ period })}`)
}

/** 건 상세. 없는 건이면 404 ApiError. */
export function getClaim(rebateId: string): Promise<ClaimDetail> {
  // 주소창에 친 값이 그대로 경로가 되는 자리라, 경로 글자로 감싼다.
  return api.get<ClaimDetail>(`/claims/${encodeURIComponent(rebateId)}`)
}

/** 전결대기 건 하나를 승인 · 반려한다. 권한 부족 403, 전결대기가 아니면 409. */
export function decideClaim(
  rebateId: string,
  body: DecisionRequest,
): Promise<ClaimDecisionResult> {
  return api.post<ClaimDecisionResult>(
    `/claims/${encodeURIComponent(rebateId)}/decision`,
    body,
  )
}

/** 재무가 지급을 지시한다. 재무가 아니면 403, 지시할 수 없는 상태면 409. */
export function orderPayment(
  rebateId: string,
  actor: string,
  role: string,
): Promise<PaymentOrderResult> {
  return api.post<PaymentOrderResult>(
    `/claims/${encodeURIComponent(rebateId)}/payment-order`,
    { actor, role },
  )
}

/** AI 검토를 사람 결정 앞까지 돌린다. 결정 대기가 아니거나 이미 검토했으면 409. */
export function reviewClaim(rebateId: string): Promise<AiReview> {
  return api.post<AiReview>(`/claims/${encodeURIComponent(rebateId)}/review`)
}

/** 정정 신고로 재검토필요가 된 건을 영업지원팀이 다시 판정한다. 재검토필요가 아니면 409. */
export function rejudgeClaim(
  rebateId: string,
  actor: string,
  role: string,
): Promise<RejudgeResult> {
  return api.post<RejudgeResult>(`/claims/${encodeURIComponent(rebateId)}/rejudge`, {
    actor,
    role,
  })
}
