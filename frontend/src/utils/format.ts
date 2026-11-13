/**
 * 표시용 포맷 함수. 지금은 원화 금액만 있다(날짜는 처음 쓰는 화면에서 더한다).
 */

/** 3888097 → "3,888,097원". 지역을 적지 않으면 브라우저 설정을 따라 3.888.097 이 될 수 있다. */
export function formatKrw(amount: number): string {
  return `${amount.toLocaleString('ko-KR')}원`
}
