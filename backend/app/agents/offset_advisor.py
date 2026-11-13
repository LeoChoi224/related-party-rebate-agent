"""AI 상계액 추천(22): 구조화 출력 한 번 → 가드 → (문제면 1회 다시) → 2회 실패나 모델 없음이면 대체 모드.

그래프로 만들지 않은 이유: 이 추천 뒤의 기다림(재무 결정 · 대리점 동의 [모의])은 업무 상태
(상계검토 + 제안 상태)로 DB 에 이미 남는다. 체크포인트에 같은 것을 또 두면 상태가 두 곳이 된다.
DB 를 모르는 순수 호출이다. 사실(facts)을 만들고 결과를 저장하는 일은 services/offset.py 가 한다.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel

from app.agents.guards import check_offset_advice
from app.agents.prompts import offset_advice_messages
from app.schemas.offset import OffsetAdvice

logger = logging.getLogger(__name__)

# 첫 답 + 다시 생성 1회(claim_review 와 같음).
MAX_ATTEMPTS = 2


@dataclass(frozen=True)
class AdviceOutcome:
    """advice 가 None 이면 대체 모드다(problems 에 이유)."""

    advice: OffsetAdvice | None
    problems: list[str] = field(default_factory=list)


def advise_offset(
    model: BaseChatModel | None, facts: dict[str, Any], *, max_offset_krw: int
) -> AdviceOutcome:
    """상계액을 추천받는다. 한도를 넘거나 형식이 틀리면 문제를 알려 한 번 더 묻는다."""
    if model is None:
        return AdviceOutcome(None, ["LLM 키가 없어 대체 모드"])
    problems: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        messages = offset_advice_messages(facts, problems)
        try:
            advice = model.with_structured_output(OffsetAdvice).invoke(messages)
        # 네트워크 · 시간 초과 · 형식 오류 등 무엇이든 실패 1회로 친다.
        except Exception as e:  # noqa: BLE001
            logger.warning("offset advice LLM call failed (attempt %d): %s", attempt, e)
            problems = ["AI 호출 실패"]
            continue
        guard = check_offset_advice(advice, max_offset_krw=max_offset_krw)
        if guard.ok:
            return AdviceOutcome(advice)
        logger.info(
            "상계 추천 가드 실패(%d회차): %s", attempt, "; ".join(guard.problems)
        )
        problems = guard.problems
    return AdviceOutcome(None, problems)
