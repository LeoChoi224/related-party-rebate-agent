/**
 * 관련자 근거 타입. 백엔드 schemas/related_party.py 와 맞춘다.
 */
import type { RelationJudgement } from './enums.ts'

/** 일치한 속성 하나. refs_a · refs_b 는 양쪽 근거 행("파일:행")이다. */
export type MatchedAttr = {
  attr: string
  value: string
  refs_a: string[]
  refs_b: string[]
}

/** 1개 이상 일치한 두 대리점. agency_a 가 작은 ID 다. */
export type RelationEdge = {
  agency_a: string
  agency_b: string
  judgement: RelationJudgement
  match_count: number
  matched_attrs: MatchedAttr[]
}
