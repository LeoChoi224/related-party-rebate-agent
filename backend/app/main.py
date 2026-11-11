"""FastAPI 앱 진입점.

앱 객체를 만들고 API 라우터를 등록한다.
시작할 때 원본 CSV로 DB 초기 상태를 만들고(seed),
배포 모드에서는 React 빌드 결과(frontend/dist)를 정적 파일로 함께 내보낸다.
"""
