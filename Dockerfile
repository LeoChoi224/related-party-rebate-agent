# 1단계: React 화면을 빌드한다 (결과물은 frontend/dist).
FROM node:24-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 2단계: FastAPI 가 /api 와 빌드된 화면을 함께 내보낸다.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
# 앱이 켜질 때 이 원본으로 업무 DB 를 다시 만든다. 쓰는 4개 파일이 든 01_corevia 만 넣는다.
COPY 01_참가자_배포용/04_원본데이터/01_corevia 01_참가자_배포용/04_원본데이터/01_corevia
COPY --from=frontend /app/frontend/dist frontend/dist

WORKDIR /app/backend
EXPOSE 8080
# AXHub 가 PORT 환경변수로 포트를 정해 준다. 0.0.0.0 으로 열어야 바깥에서 접속된다.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
