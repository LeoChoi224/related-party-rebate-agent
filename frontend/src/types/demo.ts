/**
 * 시연 패널 응답 타입. 백엔드 schemas/demo.py 와 맞춘다.
 */

/** 초기화 결과: 표 이름별로 다시 채운 행 수. */
export type ResetResult = {
  counts: Record<string, number>
}
