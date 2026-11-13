"""pytest 공통 픽스처: 원본 데이터로 채운 임시 업무 DB, AI 검토용 가짜 모델."""

import pytest

from app.core.database import make_engine
from app.seed.seeder import reset_database


@pytest.fixture
def seeded_engine(tmp_path):
    """원본 CSV 로 초기화한 임시 파일 DB. 실제 app.db 는 건드리지 않는다."""
    eng = make_engine(f"sqlite:///{tmp_path / 'seeded.db'}")
    reset_database(eng)
    yield eng
    eng.dispose()


class FakeReviewModel:
    """채팅 모델의 with_structured_output(...).invoke(...) 만 흉내 낸다. 네트워크에 나가지 않는다.

    넣어 둔 답(dict)을 부를 때마다 차례로 돌려주고, 예외를 넣어 두면 그 차례에 던진다.
    """

    model_name = "fake-review"

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return self.schema.model_validate(answer)


@pytest.fixture
def fake_model():
    """FakeReviewModel(답1, 답2, ...) 를 만드는 함수."""
    return FakeReviewModel
