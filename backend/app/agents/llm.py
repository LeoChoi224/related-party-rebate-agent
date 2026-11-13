"""LLM 게이트웨이.

설정에 따라 LangChain 채팅 모델을 만든다. 지금은 OpenAI 만 쓴다.
회사를 늘리려면 _API_KEYS 에 한 줄, requirements 에 그 회사 패키지를 더한다.
회사가 비었거나 · 모르는 회사이거나 · 키가 없으면 None 을 돌려주고, 쓰는 쪽은 대체 모드
(AI 추천 없이 규정 결과만)로 간다. 호출 실패와 다시 생성은 그래프의 가드가 다룬다(17).
"""

import logging
from collections.abc import Callable

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# 회사 이름 → 그 회사 키를 설정에서 꺼내는 함수. 여기 있는 회사만 지원한다.
_API_KEYS: dict[str, Callable[[Settings], SecretStr]] = {
    "openai": lambda s: s.openai_api_key,
}

# 기본값은 늦은 응답을 오래 기다리고 여러 번 다시 보내 시연 중 버튼이 멈춘다.
TIMEOUT_SECONDS = 30
MAX_RETRIES = 1


def get_chat_model(settings: Settings | None = None) -> BaseChatModel | None:
    """채팅 모델을 만든다. 쓸 수 없으면 이유를 남기고 None. 만들기만 하고 부르지 않는다."""
    settings = settings or get_settings()
    provider = settings.llm_provider.strip().lower()

    if not provider:
        logger.info("LLM_PROVIDER 가 비어 있어 대체 모드로 동작합니다")
        return None
    if provider not in _API_KEYS:
        logger.warning("지원하지 않는 LLM 회사 '%s' — 대체 모드로 동작합니다", provider)
        return None
    api_key = _API_KEYS[provider](settings).get_secret_value()
    if not api_key:
        logger.warning("%s_API_KEY 가 없어 대체 모드로 동작합니다", provider.upper())
        return None

    # temperature 는 넣지 않는다. gpt-5 계열은 기본값(1) 말고는 받지 않는다.
    return init_chat_model(
        settings.llm_model,
        model_provider=provider,
        api_key=api_key,
        timeout=TIMEOUT_SECONDS,
        max_retries=MAX_RETRIES,
    )
