"""pytest 공통 픽스처: 원본 데이터로 채운 임시 업무 DB."""

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
