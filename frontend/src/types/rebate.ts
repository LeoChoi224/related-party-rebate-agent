/**
 * 장려금 건 응답 타입. 백엔드 schemas/rebate.py 와 맞춘다.
 * 지금은 접수 결과만 둔다. 처리함 목록 · 건 상세 타입은 13 · 14 에서 더한다.
 */

/** 대상월 접수 요약. 이름은 서버 JSON 그대로(snake_case) 둔다. */
export type IntakeResult = {
  period_ym: string
  received: number
  by_status: Record<string, number>
}
