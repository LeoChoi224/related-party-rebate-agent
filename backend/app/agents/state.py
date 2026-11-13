"""그래프 상태 타입 정의(TypedDict).

체크포인터가 상태를 저장하므로 값은 dict · list · 문자열 · 숫자처럼 단순하게 둔다(Pydantic 객체 대신 model_dump).
업무 상태(건 상태 · 결정)의 기준은 업무 DB 다. 여기에는 그래프가 다음 노드로 넘길 값만 둔다.
"""

from typing import Any, TypedDict


class ClaimReviewState(TypedDict, total=False):
    # 대상: 검토를 시작한 건과 그 건의 검토 단위(건 하나 또는 승인 요청 하나)
    rebate_id: str
    target_type: str
    target_id: str
    # 조회 결과와 코드 계산값
    facts: dict[str, Any]
    group_sum_krw: int
    min_authority: str
    # AI 출력과 가드 결과. assessment 는 ClaimAssessment.model_dump(), 대체 모드면 None.
    llm_available: bool
    attempts: int
    assessment: dict[str, Any] | None
    problems: list[str]
    authority_raised: bool
    fallback_used: bool
    # 저장한 추천 행과 사람 결정({"decision", "reason", "actor"})
    rec_id: int
    decision: dict[str, str]


class ExplanationReviewState(TypedDict, total=False):
    # 대상: 검토할 소명 회신과 그 회신이 속한 건 · 대리점
    reply_id: int
    rebate_id: str
    agency_id: str
    facts: dict[str, Any]
    llm_available: bool
    # 회신에서 뽑은 주장과 대조 진행. cursor 는 다음에 대조할 주장 번호(0부터).
    claims: list[str]
    extract_failed: bool
    cursor: int
    # 주장별 대조 결과: {"seq", "claim_text", "verdict", "finding", "tool_used", "evidence_ref"}
    checks: list[dict[str, Any]]
    # 종합 판단(ExplanationAssessment.model_dump()), 대체 모드면 None
    attempts: int
    assessment: dict[str, Any] | None
    problems: list[str]
    fallback_used: bool
    # 사람 확인({"judgement", "reason", "actor"})
    decision: dict[str, str]
