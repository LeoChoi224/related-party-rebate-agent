/**
 * 표시용 포맷 함수: 원화 금액, 시각.
 */

/** 3888097 → "3,888,097원". 지역을 적지 않으면 브라우저 설정을 따라 3.888.097 이 될 수 있다. */
export function formatKrw(amount: number): string {
  return `${amount.toLocaleString('ko-KR')}원`
}

/**
 * "2026-11-13T05:12:05Z" → "2026. 11. 13. 14:12:05".
 * 보는 컴퓨터의 시간대와 상관없이 한국 시각으로 보여 준다.
 */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}
