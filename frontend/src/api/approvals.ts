/**
 * 상신 API: 승인 요청 결정(영업임원 승인 · 반려). 요청의 포함 건이 함께 바뀐다.
 * 승인 요청 칸은 건 상세 응답에 실려 오므로 따로 조회하지 않는다(14 결정).
 */
import type { ApprovalDecisionResult, DecisionRequest } from '../types/approval.ts'
import { api } from './client.ts'

/** 승인 요청을 결정한다. 권한 부족 403, 이미 결정된 요청 409, 사유 없는 반려 422. */
export function decideApproval(
  requestId: number,
  body: DecisionRequest,
): Promise<ApprovalDecisionResult> {
  return api.post<ApprovalDecisionResult>(`/approvals/${requestId}/decision`, body)
}
