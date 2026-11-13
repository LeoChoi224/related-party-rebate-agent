"""시연 API.

지금은 초기화만 있다. 시나리오 이벤트 주입은 그 기능을 만드는 브랜치(26)에서 더한다.
시연 관리자 역할 검사는 하지 않는다. 역할은 화면이 스스로 적어 보내는 값이라 확인할 근거가 없다.
화면은 시연 패널 메뉴를 시연 관리자에게만 보여 준다. 실제 시스템이면 로그인 토큰의 역할로 막는다.
"""

from fastapi import APIRouter, Request

from app.schemas.demo import ResetResult
from app.seed.seeder import reset_database

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/reset")
def reset(request: Request) -> ResetResult:
    """업무 DB 를 원본으로 되돌린다. 앱을 켤 때와 같은 동작이다."""
    # SQLite 쓰기는 끝날 때까지 스레드를 막는다. async def 가 아니라 def 로 두면
    # FastAPI 가 별도 스레드에서 돌려서 그동안 다른 요청이 멈추지 않는다.
    return ResetResult(counts=reset_database(request.app.state.engine))
