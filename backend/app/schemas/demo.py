"""시연 패널 응답.

지금은 초기화 결과만 둔다. 6월분 접수 · 정정 신고 · 소명 회신 · 은행 회신 주입은
그 기능을 만드는 브랜치에서 더한다.
"""

from pydantic import BaseModel


class ResetResult(BaseModel):
    """표 이름별로 다시 채운 행 수."""

    counts: dict[str, int]
