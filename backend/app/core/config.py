"""앱 전역 설정.

경로 상수와, .env · 환경 변수에서 읽는 설정(LLM 회사 · 모델 · 키)을 둔다.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# core → app → backend → 프로젝트 루트
BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
# 대회 원본 데이터. 읽기만 한다.
RAW_DATA_DIR = PROJECT_ROOT / "01_참가자_배포용" / "04_원본데이터"
# 업무 DB. 앱을 켤 때마다 원본으로 다시 만든다.
DB_PATH = BACKEND_DIR / "data" / "app.db"


class Settings(BaseSettings):
    """.env 와 환경 변수에서 읽는 설정. 환경 변수 이름은 대소문자를 가리지 않는다."""

    # 상대경로면 명령을 친 폴더 기준이 되어, 띄우는 위치마다 결과가 달라진다.
    # Docker 에는 .env 가 없고 환경 변수로 들어온다(파일이 없으면 환경 변수만 읽는다).
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 비어 있으면 대체 모드(AI 추천 없이 규정 결과만).
    llm_provider: str = ""
    llm_model: str = "gpt-5-mini"
    # 로그 · 오류에 실려도 '**********' 로만 보인다.
    openai_api_key: SecretStr = SecretStr("")


@lru_cache
def get_settings() -> Settings:
    """앱 전체에서 설정 객체 하나. .env 를 요청마다 다시 읽지 않는다."""
    return Settings()
