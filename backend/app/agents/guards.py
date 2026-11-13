"""AI 출력 가드.

① AI 출력의 숫자가 코드 계산값과 같은가 ② 결재 단계가 최소 결재권자 이상인가 ③ 출력 형식이 맞는가를 검사한다.
①·③ 이 틀리면 다시 생성할 대상이다. ② 는 코드가 정답을 알므로 다시 묻지 않고 코드 값으로 올리고 기록한다.
DB · 그래프를 모르는 순수 함수다.
"""

from dataclasses import dataclass, field

from app.schemas.ai_recommendation import ClaimAssessment
from app.services.approval_authority import has_authority


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    problems: list[str] = field(default_factory=list)
    authority_raised: bool = False


def check_assessment(
    assessment: ClaimAssessment, *, group_sum_krw: int, min_authority: str
) -> GuardResult:
    """AI 평가를 코드 계산값과 대조한다. 결재 단계가 낮은 것은 실패가 아니라 올림이다."""
    problems = []
    # ③ 형식: 구조화 출력이 모양은 맞춰도 값의 범위 · 빈 근거까지는 막지 못한다.
    if not 0 <= assessment.confidence <= 1:
        problems.append(f"확신도 {assessment.confidence} 이(가) 0~1 밖입니다")
    if not assessment.rationale:
        problems.append("근거가 비어 있습니다")
    # ① 숫자: 합산이 틀린 추천은 근거 문장도 틀린 숫자를 쓰고 있을 수 있다.
    if assessment.group_sum_krw != group_sum_krw:
        problems.append(
            f"AI 합산 {assessment.group_sum_krw:,}원이 코드 계산 {group_sum_krw:,}원과 다릅니다"
        )
    if problems:
        return GuardResult(ok=False, problems=problems)

    # ② 결재 단계: 09 와 같은 "요구 역할 이상" 비교를 쓴다.
    raised = not has_authority(assessment.ai_authority, min_authority)
    return GuardResult(ok=True, authority_raised=raised)
