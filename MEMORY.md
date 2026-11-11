# MEMORY — W07 판매장려금 통제 데스크

Last updated: 2026-11-11

## 지금 상태

- 업무 **W07 관련 거래처와 판매장려금 지급** 선택. 설계 문서 `docs/W07_설계안.md` v0.2 · `docs/architecture.md` v0.2(아키텍처 · 페이지 흐름 · AI 워크플로 · ERD).
- 프로젝트 폴더: `~/LeoData/MyCode/rebate-agent` (11/11 `삼일PwC_프로젝트폴더`에서 이름 변경. 기록 훅은 폴더 경로를 쓰지 않아 영향 없음).
- 뼈대: `backend/` .py 80개 · `frontend/src/` 47개 (설명 주석만, ruff format 정리됨), 폴더별 `.gitignore`. PR #1(`chore/project-skeleton`)로 main 에 머지됨.
- GitHub `LeoChoi224/related-party-rebate-agent`(`origin`, 퍼블릭). 라벨: GitHub 기본 10개(`chore` 라벨은 사용자가 만들기로 함).
- axhub CLI v0.63.0(`~/.axhub/bin/axhub`, PATH 미등록) · 플러그인 axhub@axhub 1.43.0 · 로그인 완료(leochoi224@gmail.com). lounge 테넌트 ID `c7a0a6fe-86c6-45f4-adc2-3ab7bd19ea36`.
- AXHub 앱은 아직 없음(`related-party-rebate-agent` 이름 사용 가능 상태).
- 진행 중: 로드맵 01 `chore/scaffold-fastapi-react` — Step 3 정답은 줬고, 사용자 반영 전.

## 다음에 할 일

- 01 Step 3 반영(사용자) → Claude 검증 → 커밋 · 푸시 · PR(사용자).
- 02 `chore/axhub-first-deploy`: Dockerfile · .dockerignore · axhub.yaml(승인 후 작성) → 앱 생성 · 배포 명령은 사용자가 실행 → Claude 가 배포 상태 확인 · 주소 보고.

## 결정과 근거

- 업무 W07: 판정 규칙이 숫자로 떨어지고 위반 사례(G1)가 데이터에 있음. PwC 감사 · 내부통제와 맞음.
- 스택 FastAPI + SQLite + React(Vite) + LangGraph: Python 백엔드로 수업(LangChain) 경험을 살리고, React 는 역할별 승인 화면에 맞음.
- 배포 AXHub lounge · Docker 방식 · 앱 이름 `related-party-rebate-agent`: 배포 방식은 생성 후 못 바꿈(정적→Docker만 가능), FastAPI 때문에 처음부터 Docker.
- lounge 는 코드 저장 위치가 Axhub 저장소뿐(GitHub 불가) → `origin`(GitHub)은 포트폴리오용, 배포용 Axhub 원격을 따로 둔다.
- SQLite 는 앱 시작 시 원본 CSV로 다시 만든다: AXHub 컨테이너 파일은 재배포 · 재시작 때 초기화되고, 시연 초기화와도 같은 동작.
- AI: 판단 · 추천은 AI(LangGraph 그래프 3개: claim_review · explanation_review · master_change_parser), 최종 결정은 사람. AI 는 결재 단계를 올릴 수만 있음(코드 가드). 업무 상태는 DB 한 곳.
- 필수 확장 = 지급 전 미수채권 대조 · 상계 [가정]. 다른 부서 영향 = 재무(채권 회수) · 영업(대리점 관계) · 감사(사후 검토).
- 커밋 · 푸시와 코드를 올리는 axhub 명령은 사용자가 직접 한다. 소스 코드는 Step 1→2→3 으로 사용자가 타이핑한다.
- GitHub 이슈는 쓰지 않고 로드맵 번호 · 브랜치 이름으로 관리한다(1인 · 4일 일정).
- 저장소 퍼블릭 공개: 주최 측 문의 결과 포트폴리오 · GitHub 공개 허용(11/11).
- 루트 `.gitignore`(기록 키 3줄)는 대회 규칙상 수정 금지 → 앱용 ignore 는 폴더별 파일.

## 자주 쓰는 원본 사실

- 관련자 그룹 G1 = D-011 · D-024 · D-037 (D-024 실입금계좌 = G1 공유계좌 국민 412-27-556310, DP-00013 · 14).
- G1 6월분 합산 3,888,097원 → 영업임원 상신 대상. 6월분 40건 `미지급` = 기준일(7/1) 처리할 일.
- 1~5월 G1 15건 22,238,349원이 영업지원팀 전결로 지급됨(한도 200만원 우회).
- G1 미수채권 48,481,080원(120일 넘은 연체 5건). D-034–D-041 은 대표자만 일치 → 정황.
