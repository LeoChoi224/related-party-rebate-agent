"""AI 출력 가드 테스트. 순수 함수라 DB 없이 평가를 직접 만들어 넣는다."""

from app.agents.guards import check_assessment
from app.schemas.ai_recommendation import ClaimAssessment

G1_SUM = 3_888_097


def assessment(**overrides) -> ClaimAssessment:
    values = {
        "recommendation": "승인",
        "ai_authority": "영업임원",
        "group_sum_krw": G1_SUM,
        "rationale": ["G1 합산 3,888,097원이 한도 2,000,000원을 넘음"],
        "counter_evidence": [],
        "confidence": 0.8,
    }
    return ClaimAssessment(**(values | overrides))


def check(a: ClaimAssessment, min_authority: str = "영업임원"):
    return check_assessment(a, group_sum_krw=G1_SUM, min_authority=min_authority)


def test_correct_assessment_passes():
    result = check(assessment())
    assert result.ok
    assert result.problems == []
    assert not result.authority_raised


def test_wrong_sum_fails_with_both_numbers():
    result = check(assessment(group_sum_krw=1_500_000))
    assert not result.ok
    assert result.problems == ["AI 합산 1,500,000원이 코드 계산 3,888,097원과 다릅니다"]


def test_confidence_out_of_range_and_empty_rationale_fail():
    result = check(assessment(confidence=1.5, rationale=[]))
    assert not result.ok
    assert len(result.problems) == 2


def test_lower_authority_passes_but_is_raised():
    """G1 을 전결(영업지원팀)로 판단해도 실패가 아니라 코드 값으로 올린다."""
    result = check(assessment(ai_authority="영업지원팀"))
    assert result.ok
    assert result.authority_raised


def test_higher_authority_is_not_raised():
    """AI 가 단계를 더 올려 보는 것은 허용한다(올릴 수만 있다)."""
    result = check(assessment(ai_authority="영업임원"), min_authority="영업지원팀")
    assert result.ok
    assert not result.authority_raised
