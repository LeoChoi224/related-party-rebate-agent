/**
 * 시연 시나리오 값(설계안 7장). 시연 패널(26) · 정정 신고 화면 · 소명 칸이 같은 값을 쓴다.
 * 모두 [모의] · [주장] 으로 넣는 시연용 입력이고 원본 데이터가 아니다.
 */
import type { CorrectableAttr } from '../types/masterChange.ts'

/** 시나리오 2 의 정정 신고 두 건: 결론이 유지되는 신고와 바뀌는 신고. */
export const MASTER_CHANGE_DEMOS = [
  {
    label: 'D-037 정산계좌 변경(그룹 유지)',
    agencyId: 'D-037',
    attrType: '등록계좌' as CorrectableAttr,
    newValue: '신한 123-45-678901',
    reportedText: '정산 계좌를 신한은행으로 옮겼습니다.',
  },
  {
    label: 'D-041 주소 정정(새 그룹)',
    agencyId: 'D-041',
    attrType: '주소' as CorrectableAttr,
    newValue: '대전시 중앙로 260',
    reportedText: '본사를 대전시 중앙로 260 으로 이전했습니다.',
  },
]

/** 시나리오 3 의 대리점 소명 회신 [모의]. 입금 기록과 대조하면 맞지 않는 설명이다(설계안 4-2). */
export const DEMO_REPLY = 'D-024는 별도 법인이고, 계좌가 겹친 건 세무대리인이 대신 입금해서입니다.'

/** 시나리오 3 에서 영업임원이 반려하며 요청하는 소명 항목. */
export const DEMO_EXPLANATION_ITEMS = ['D-024 와 같은 계좌로 입금된 경위', '별도 법인임을 보여 주는 증빙']

/** 관련자 그룹 G1 의 6월분 건(D-011 · D-024 · D-037). */
export const G1_JUNE_CLAIMS = ['RB-00054', 'RB-00120', 'RB-00180']
