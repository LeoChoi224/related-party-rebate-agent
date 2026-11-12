"""앱 전역 설정.

지금은 경로만 둔다. .env 값(LLM 키 등)은 필요해지는 브랜치에서 추가한다.
"""

from pathlib import Path

# core → app → backend → 프로젝트 루트
BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
# 대회 원본 데이터. 읽기만 한다.
RAW_DATA_DIR = PROJECT_ROOT / "01_참가자_배포용" / "04_원본데이터"
# ===================== 추가: 업무 DB 파일 경로 =====================
# 업무 DB. 앱을 켤 때마다 원본으로 다시 만든다.
DB_PATH = BACKEND_DIR / "data" / "app.db"
# ==================================================================
