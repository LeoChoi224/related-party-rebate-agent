/**
 * 상계 API [가정]: AI 상계액 추천, 재무 결정, 대리점 동의 [모의].
 * 제안은 그룹 건이 승인될 때 서버가 만들고, 조회는 건 상세의 offsets 칸으로 한다.
 */
import type { AgencyConsent } from '../types/enums.ts'
import type { OffsetDecisionBody, OffsetProposal, OffsetResult } from '../types/offset.ts'
import { api } from './client.ts'

/** AI 상계액 추천을 받는다. LLM 을 부르므로 몇 초 걸릴 수 있다. 재무 결정 뒤면 409. */
export function recommendOffset(offsetId: number): Promise<OffsetProposal> {
  return api.post<OffsetProposal>(`/offsets/${offsetId}/recommend`)
}

/** 재무가 상계액을 정하거나 상계하지 않기로 한다. 재무 아님 403, 이미 결정 409, 한도 밖 422. */
export function decideOffset(offsetId: number, body: OffsetDecisionBody): Promise<OffsetResult> {
  return api.post<OffsetResult>(`/offsets/${offsetId}/decision`, body)
}

/** 대리점 회신을 시연으로 넣는다. 동의면 채권 잔액이 줄고, 전액 상계면 건이 상계완료가 된다. */
export function sendAgencyConsent(
  offsetId: number,
  consent: AgencyConsent,
): Promise<OffsetResult> {
  return api.post<OffsetResult>(`/offsets/${offsetId}/agency-consent`, { consent })
}
