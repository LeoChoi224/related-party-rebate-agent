"""LLM 게이트웨이 테스트.

설정은 항상 값을 넣어 만든다(_env_file=None). 개발자 컴퓨터의 .env · 환경 변수에
진짜 키가 있어도 테스트 결과가 달라지지 않게 하려는 것이다. 네트워크 호출은 없다.
"""

import logging

import pytest
from langchain_openai import ChatOpenAI

from app.agents.llm import get_chat_model
from app.core.config import Settings

LOGGER = "app.agents.llm"


def make_settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


@pytest.fixture(autouse=True)
def no_llm_env(monkeypatch):
    """환경 변수에 진짜 값이 있어도 테스트에 섞이지 않게 지운다."""
    for name in ("LLM_PROVIDER", "LLM_MODEL", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_empty_provider_is_fallback(caplog):
    """회사가 비었으면 키가 있어도 대체 모드."""
    with caplog.at_level(logging.INFO, logger=LOGGER):
        model = get_chat_model(make_settings(openai_api_key="sk-test"))
    assert model is None
    assert "대체 모드" in caplog.text


def test_unknown_provider_is_fallback_with_reason(caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        model = get_chat_model(
            make_settings(llm_provider="nope", openai_api_key="sk-test")
        )
    assert model is None
    assert "지원하지 않는 LLM 회사 'nope'" in caplog.text


def test_missing_key_is_fallback_with_reason(caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        model = get_chat_model(make_settings(llm_provider="openai"))
    assert model is None
    assert "OPENAI_API_KEY" in caplog.text


def test_provider_and_key_make_openai_model_without_calling():
    """가짜 키로도 모델 객체는 만들어진다(부르지 않으므로 네트워크에 나가지 않음)."""
    model = get_chat_model(
        make_settings(
            llm_provider=" OpenAI ", llm_model="gpt-5-mini", openai_api_key="sk-test"
        )
    )
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "gpt-5-mini"
    assert model.max_retries == 1


def test_settings_reads_env_and_hides_key(monkeypatch):
    """환경 변수 이름은 대문자로 들어와도 읽히고, 키는 표시에 드러나지 않는다."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-123")
    settings = make_settings()
    assert settings.llm_provider == "openai"
    assert settings.openai_api_key.get_secret_value() == "sk-secret-123"
    assert "sk-secret-123" not in repr(settings)
