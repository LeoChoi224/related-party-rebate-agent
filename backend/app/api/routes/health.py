"""상태 확인 API.

AXHub 가 배포 뒤 앱이 살아 있는지 이 경로로 확인한다. DB 를 부르지 않고 바로 응답한다.
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
