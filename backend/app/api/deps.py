"""라우터 공통 의존성.

요청 하나 = 트랜잭션 하나: 정상으로 끝나면 commit, 예외가 나면 롤백한다.
서비스(services/*)는 commit 하지 않고 이 트랜잭션 안에서 함께 확정 · 취소된다.
AI 검토 모델도 의존성으로 넣는다. 테스트가 dependency_overrides 로 가짜 모델을 넣는다.
역할은 여기서 확인하지 않는다. 역할 · 이름은 화면이 요청 본문에 넣는 값이고(09),
결재 · 지급 권한(403)은 서비스가 그 값으로 검사한다. 실제 시스템이면 로그인 토큰에서 꺼낸다.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from langchain_core.language_models import BaseChatModel
from sqlalchemy.orm import Session

from app.agents.llm import get_chat_model


def get_session(request: Request) -> Iterator[Session]:
    """요청마다 세션과 트랜잭션을 연다. 라우트에서 난 예외는 yield 자리에서 다시 터진다."""
    # 테스트가 create_app(engine=...) 으로 넣은 임시 엔진을 쓰려고 app.state 에서 꺼낸다.
    with Session(request.app.state.engine) as session, session.begin():
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def get_review_model() -> BaseChatModel | None:
    """AI 검토에 쓸 모델. 키가 없으면 None 이고 그래프는 대체 모드로 돈다."""
    return get_chat_model()


ReviewModelDep = Annotated[BaseChatModel | None, Depends(get_review_model)]
