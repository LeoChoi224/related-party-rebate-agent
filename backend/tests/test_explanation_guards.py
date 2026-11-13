"""소명 가드 테스트: 근거 없는 판정은 확인불가로 내리고, 증빙 충분은 모든 주장이 일치할 때만 허용한다."""

from app.agents.guards import check_claim_result, check_explanation_assessment
from app.schemas.explanation import CheckResult, ExplanationAssessment

REF = "fin_collection_history_cv.csv:14"


def check(verdict="불일치", refs=None) -> CheckResult:
    return CheckResult(
        verdict=verdict,
        finding="대조 결과",
        evidence_refs=[REF] if refs is None else refs,
    )


def assessment(**overrides) -> ExplanationAssessment:
    values = {
        "judgement": "증빙 부족",
        "rationale": ["입금 계좌가 D-011 등록계좌 (fin_collection_history_cv.csv:14)"],
        "missing_evidence": ["입금 대행 계약서"],
        "follow_up_request": "입금 대행 계약서와 세무대리인 계좌 명의를 보내 주세요",
        "confidence": 0.8,
    }
    return ExplanationAssessment(**(values | overrides))


def test_claim_with_real_reference_keeps_verdict():
    result = check_claim_result(check(), {REF, "other.csv:1"})
    assert (result.verdict, result.evidence_refs, result.downgraded) == (
        "불일치",
        [REF],
        False,
    )


def test_invented_reference_is_dropped_and_verdict_downgraded():
    """도구가 돌려주지 않은 근거 행만 인용한 불일치는 확인불가로 내린다."""
    result = check_claim_result(check(refs=["made_up.csv:99"]), {REF})
    assert (result.verdict, result.evidence_refs, result.downgraded) == (
        "확인불가",
        [],
        True,
    )


def test_consistent_without_any_evidence_is_downgraded():
    result = check_claim_result(check("일치", refs=[]), {REF})
    assert result.verdict == "확인불가" and result.downgraded


def test_unverifiable_needs_no_evidence_and_is_not_marked_downgraded():
    result = check_claim_result(check("확인불가", refs=[]), set())
    assert (result.verdict, result.downgraded) == ("확인불가", False)


def test_duplicate_references_are_collapsed_in_order():
    result = check_claim_result(check(refs=[REF, REF, "b.csv:2"]), {REF, "b.csv:2"})
    assert result.evidence_refs == [REF, "b.csv:2"]


def test_insufficient_with_mismatch_passes():
    checks = [{"verdict": "불일치"}]
    assert check_explanation_assessment(assessment(), checks).ok


def test_sufficient_with_a_mismatch_is_a_problem():
    result = check_explanation_assessment(
        assessment(judgement="증빙 충분", follow_up_request=""), [{"verdict": "불일치"}]
    )
    assert not result.ok and "모두 데이터와 일치" in result.problems[0]


def test_sufficient_without_checked_claims_is_a_problem():
    """주장을 하나도 확인하지 못했는데 충분하다고 할 수는 없다."""
    result = check_explanation_assessment(
        assessment(judgement="증빙 충분", follow_up_request=""), []
    )
    assert not result.ok


def test_sufficient_with_all_consistent_passes():
    result = check_explanation_assessment(
        assessment(judgement="증빙 충분", follow_up_request=""),
        [{"verdict": "일치"}, {"verdict": "일치"}],
    )
    assert result.ok


def test_insufficient_needs_follow_up_request():
    result = check_explanation_assessment(
        assessment(follow_up_request="  "), [{"verdict": "불일치"}]
    )
    assert not result.ok and "추가 요청문" in result.problems[0]


def test_confidence_range_and_empty_rationale_are_checked():
    result = check_explanation_assessment(
        assessment(confidence=1.5, rationale=[]), [{"verdict": "불일치"}]
    )
    assert len(result.problems) == 2
