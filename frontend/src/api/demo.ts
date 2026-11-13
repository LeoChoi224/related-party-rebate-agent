/**
 * 시연 패널 API. 지금은 초기화만 있다. 시나리오 이벤트 넣기는 26 에서 더한다.
 */
import type { ResetResult } from '../types/demo.ts'
import { api } from './client.ts'

/** 업무 DB 를 원본으로 되돌린다. */
export function resetDemo(): Promise<ResetResult> {
  return api.post<ResetResult>('/demo/reset')
}
