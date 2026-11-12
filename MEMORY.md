# MEMORY — W07 판매장려금 통제 데스크

Last updated: 2026-11-11 21:00

## 지금 상태

- 업무 **W07 관련 거래처와 판매장려금 지급**. 설계 `docs/W07_설계안.md` v0.2 · `docs/architecture.md` v0.2(아키텍처 · 페이지 흐름 · AI 워크플로 · ERD).
- 프로젝트 폴더 `~/LeoData/MyCode/rebate-agent` (11/11 `삼일PwC_프로젝트폴더`에서 이름 변경. 기록 훅은 폴더 경로를 쓰지 않아 영향 없음).
- 원격: `origin` = Axhub 저장소(배포용, `main` push 시 자동 배포), `github` = GitHub `LeoChoi224/related-party-rebate-agent`(퍼블릭, PR 용). 라벨: GitHub 기본 10개 + `chore`.
- axhub CLI v0.63.0(`~/.axhub/bin/axhub`, PATH 미등록) · 플러그인 axhub@axhub 1.43.0 · 로그인(leochoi224@gmail.com). lounge 테넌트 `c7a0a6fe-86c6-45f4-adc2-3ab7bd19ea36`.
- AXHub 앱 `related-party-rebate-agent`(Docker, 앱 ID `6a0fd4bd-b4cf-45eb-865c-dff1dfd8047a`), 주소 https://related-party-rebate-agent-h6nw.axhub.app . 배포본 = `750dfd5`(01 최소 앱 + 02 배포 설정). **절전 중**(11/11 20:20 KST부터).
- GitHub: PR #1(뼈대) · PR #2(01·02 + 메모리) 머지됨. `github/main` = `4e0cb6e`.
- 로컬: `main` = `750dfd5` 로 `github/main` 보다 2커밋 뒤. 작업 폴더에 커밋 전 변경 — 메모리 3개(`9ea829f` 이후 추가 수정: Step 4 규칙 등) + 03 코드 5개.
- 로드맵 완료: 00 · 01 · 02. 03 `feat/data-loader` 는 Step 4 반영 · 검증 완료(테스트 27개), 커밋 전.

## 다음에 할 일

- 03 커밋 · PR (사용자). 메모리 파일이 `9ea829f` 보다 새 버전이라 `main` 에서 바로 pull 하면 멈춘다 → `feat/data-loader` 브랜치에서 03 코드 · 메모리를 따로 커밋 → `git merge -X ours github/main` → `git push -u github feat/data-loader` → PR(Create a merge commit) → `git switch main` · `git pull github main`. 임시 복제본에서 충돌 없이 끝나는 것 확인(11/11).
- 04 `feat/db-schema` Step 1 — 원본 폴더를 Docker 이미지에 넣는 Dockerfile 수정 포함(설정 파일, 승인 필요).
- 제출 전 앱 `wake` 후 심사 기간 내내 켜 두기.

## 결정과 근거

- 업무 W07: 판정 규칙이 숫자로 떨어지고 위반 사례(G1)가 데이터에 있음. PwC 감사 · 내부통제와 맞음.
- 스택 FastAPI + SQLite + React(Vite) + LangGraph. FastAPI 하나가 `/api` 와 React 빌드를 함께 서빙(주소 1개). 없는 화면 주소는 index.html, 없는 `/api` 는 404.
- 배포 AXHub lounge · Docker · 앱 이름 `related-party-rebate-agent`(과제 핵심 "관련 거래처"가 이름에 드러나게, 폴더만 짧게). 배포 방식은 생성 후 못 바꿈.
- lounge 는 코드 저장 위치가 Axhub 저장소뿐 → GitHub 원격 이름을 `github` 로 바꾸고 `origin` 을 Axhub 저장소에 넘김(11/11).
- SQLite 는 앱 시작 시 원본 CSV로 다시 만든다(컨테이너 파일은 재배포 · 재시작 때 초기화, 시연 초기화와 같은 동작).
- AI: 판단 · 추천은 AI(LangGraph 그래프 3개: claim_review · explanation_review · master_change_parser), 최종 결정은 사람. AI 는 결재 단계를 올릴 수만 있음(코드 가드). 업무 상태는 DB 한 곳.
- 필수 확장 = 지급 전 미수채권 대조 · 상계 [가정]. 다른 부서 영향 = 재무(채권 회수) · 영업(대리점 관계) · 감사(사후 검토).
- 진행 방식: Step 1→2→3 은 블록으로 받아 대조, **Step 4 에서 Claude 가 정답(메인 · 테스트)을 파일에 반영하고 Git 명세서를 준다**(11/11). 커밋 · 푸시와 코드를 올리는 axhub 명령은 사용자가 직접.
- 원본 로더: pandas 대신 표준 `csv` + Pydantic(행마다 출처 · 오류 위치 · 빈 값/열 개수 검사, 이미지 크기). `period_ym` 은 문자열, `NONE` 은 None, 틀린 행은 건너뛰지 않고 멈춤. 미수채권은 146행 전부 읽고 대리점 필터는 쓰는 쪽에서.
- 파이썬 의존성은 leo-dev 설치 버전으로 고정(fastapi 0.141.1, uvicorn 0.52.1) — 로컬과 Docker 동일. 테스트 도구는 `requirements-dev.txt` 로 분리.
- GitHub 이슈는 쓰지 않고 로드맵 번호 · 브랜치 이름으로 관리(1인 · 4일 일정). 저장소 퍼블릭 공개는 주최 측 허용(11/11).
- 루트 `.gitignore`(기록 키 3줄)는 대회 규칙상 수정 금지 → 앱용 ignore 는 폴더별 파일, axhub 로컬 상태 `.axhub/` 는 `.git/info/exclude`.

## 자주 쓰는 원본 사실

- 관련자 그룹 G1 = D-011 · D-024 · D-037 (D-024 실입금계좌 = G1 공유계좌 국민 412-27-556310, DP-00013 · 14 = 원본 14 · 15행).
- G1 6월분 합산 3,888,097원 → 영업임원 상신 대상. 6월분 40건 `미지급` = 기준일(7/1) 처리할 일.
- 1~5월 G1 15건 22,238,349원이 영업지원팀 전결로 지급됨(한도 200만원 우회).
- G1 미수채권 48,481,080원(120일 넘은 연체 5건). D-034–D-041 은 대표자만 일치 → 정황.
- 원본 행 수: 대리점 50 · 장려금 240(approver NONE 40, payment_date NONE 44) · 입금 32 · 미수채권 146(대리점 74 + 고객 72).
