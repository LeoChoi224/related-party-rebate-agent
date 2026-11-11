"""explanation_review 그래프: 소명 검토 에이전트.

extract_claims(회신 속 주장) → check_claim(주장마다 도구로 조회·대조, 반복)
→ assess(타당성·부족 증빙·추가 요청문) → verify → human_decision(interrupt) → apply.
"""
