"""여러 응답이 함께 쓰는 필드 타입."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator


def _as_utc(value: datetime) -> datetime:
    # SQLite CURRENT_TIMESTAMP 는 UTC 를 시간대 표시 없이 저장한다.
    # 그대로 내보내면 브라우저가 한국 시각으로 읽어 9시간 이르게 보인다.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


# JSON 에 "…Z" 가 붙어 나가는 시각. DB 에서 읽은 시각은 이 타입으로 내보낸다.
UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]
