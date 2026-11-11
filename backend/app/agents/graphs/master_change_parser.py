"""master_change_parser 그래프: 정정 신고 해석.

parse(문장 → 대리점·속성·이전 값·새 값) → verify(존재·이전 값 일치)
→ human_decision(interrupt) → apply_change(그룹 재계산, 영향 건마다 claim_review 재실행).
"""
