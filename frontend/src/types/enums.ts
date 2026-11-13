/**
 * 코드 값. 백엔드 backend/app/models/enums.py 와 글자까지 같은 한글 값이다.
 *
 * tsconfig 의 erasableSyntaxOnly 때문에 TypeScript enum 은 쓸 수 없다.
 * 값 객체(as const)와 같은 이름의 유니온 타입을 짝으로 둔다.
 * 값으로는 ClaimStatus.PAID, 타입으로는 ClaimStatus('미접수' | '접수' | …) 로 쓴다.
 */

export const ClaimStatus = {
  NOT_RECEIVED: '미접수',
  RECEIVED: '접수',
  RELATION_CHECKED: '관계확인',
  AWAITING_SUPPORT: '전결대기',
  AWAITING_EXECUTIVE: '상신대기',
  AWAITING_EXPLANATION: '소명대기',
  ON_HOLD: '지급보류',
  APPROVED: '승인',
  REJECTED: '반려',
  OFFSET_REVIEW: '상계검토',
  PAYMENT_ORDERED: '지급지시',
  PAID: '지급완료',
  OFFSET_DONE: '상계완료',
  NEEDS_REVIEW: '재검토필요',
} as const
export type ClaimStatus = (typeof ClaimStatus)[keyof typeof ClaimStatus]

export const ApproverRole = {
  SALES_SUPPORT: '영업지원팀',
  SALES_EXECUTIVE: '영업임원',
} as const
export type ApproverRole = (typeof ApproverRole)[keyof typeof ApproverRole]

export const Decision = {
  APPROVE: '승인',
  REJECT: '반려',
} as const
export type Decision = (typeof Decision)[keyof typeof Decision]

export const Department = {
  FINANCE: '재무',
  SALES_SUPPORT: '영업지원팀',
  AUDIT: '내부감사',
} as const
export type Department = (typeof Department)[keyof typeof Department]

export const TaskStatus = {
  OPEN: '열림',
  IN_PROGRESS: '진행',
  DONE: '완료',
} as const
export type TaskStatus = (typeof TaskStatus)[keyof typeof TaskStatus]

export const PaymentStatus = {
  AWAITING_REPLY: '회신대기',
  SUCCEEDED: '성공',
  ACCOUNT_ERROR: '계좌오류',
} as const
export type PaymentStatus = (typeof PaymentStatus)[keyof typeof PaymentStatus]

export const BankResult = {
  SUCCESS: '성공',
  ACCOUNT_ERROR: '계좌오류',
} as const
export type BankResult = (typeof BankResult)[keyof typeof BankResult]

export const Provenance = {
  ORIGINAL: '원본',
  CLAIMED: '주장',
  ASSUMED: '가정',
  MOCK: '모의',
} as const
export type Provenance = (typeof Provenance)[keyof typeof Provenance]

export const RelationJudgement = {
  RELATED: '관련자',
  CIRCUMSTANTIAL: '정황',
} as const
export type RelationJudgement = (typeof RelationJudgement)[keyof typeof RelationJudgement]
