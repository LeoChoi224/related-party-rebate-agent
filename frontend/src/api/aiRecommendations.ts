/**
 * AI 추천 기록 API(25): 세 AI 의 출력 · 사람 결정 · 일치율.
 */
import type { AiLog } from '../types/aiRecommendation.ts'
import { api } from './client.ts'

/** 최신순 기록과 종류별 · 전체 일치율. */
export function getAiLog(): Promise<AiLog> {
  return api.get<AiLog>('/ai/recommendations')
}
