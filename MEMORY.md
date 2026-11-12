# MEMORY — W07 판매장려금 통제 데스크

Last updated: 2026-11-12

## 지금 상태

- 업무 **W07 관련 거래처와 판매장려금 지급**. 설계 `docs/W07_설계안.md` v0.2 · `docs/architecture.md` v0.2(아키텍처 · 페이지 흐름 · AI 워크플로 · ERD).
- 프로젝트 폴더 `~/LeoData/MyCode/rebate-agent` (11/11 `삼일PwC_프로젝트폴더`에서 이름 변경. 기록 훅은 폴더 경로를 쓰지 않아 영향 없음).
- 원격: `origin` = Axhub 저장소(배포용, `main` push 시 자동 배포), `github` = GitHub `LeoChoi224/related-party-rebate-agent`(퍼블릭, PR 용). 라벨: GitHub 기본 10개 + `chore`.
- axhub CLI v0.63.0(`~/.axhub/bin/axhub`, PATH 미등록) · 플러그인 axhub@axhub 1.43.0 · 로그인(leochoi224@gmail.com). lounge 테넌트 `c7a0a6fe-86c6-45f4-adc2-3ab7bd19ea36`.
- AXHub 앱 `related-party-rebate-agent`(Docker, 앱 ID `6a0fd4bd-b4cf-45eb-865c-dff1dfd8047a`), 주소 https://related-party-rebate-agent-h6nw.axhub.app . 배포본 = `750dfd5`(01 최소 앱 + 02 배포 설정). **절전 중**(11/11 20:20 KST부터).
- GitHub: PR #1(뼈대) ~ #7(07 상태 머신) 머지됨. `github/main` = `d827c54`.
- 로컬: `main` = `d827c54`. 08 작업 브랜치 `feat/intake-june-batch` 는 사용자가 만들 차례(11/12 기준 아직 `main` 위). 로컬 `main` 의 upstream 은 `origin/main`(Axhub, `750dfd5`)이라 GitHub 머지분은 반드시 `git pull github main` 으로 받는다.
- 로드맵 완료: 00 ~ 07. 04 = SQLite 원본 5개 표 · 시작 시 초기화 · `POST /api/demo/reset`. 05 = 관련자 판정(표 4개, 시더가 버전 1 저장). 06 = 한도 판정(`assess_period(session, period_ym)`). 07 = 상태 14개 · 전이표 · `transition`(이력 `event_log`, pytest 130개, `docs/architecture.md` 5장 상태도). 로컬 Docker 빌드는 미확인.
- 08 `feat/intake-june-batch` Step 1~4 끝(세션 의존성 · 409 처리기 → 접수 서비스 → `POST /api/claims/intake?period=`). 11/12 Step 4 반영 · 검증(ruff 통과, pytest 149개, uvicorn 으로 200 · 409 · 404 · 422 · 초기화 뒤 200 확인), **커밋 전**(`main` 위 작업 폴더). 첫 업무 API.
- 확인 숫자: agency 50 · identity_attr 182 · deposit 32 · ar_item 146 · rebate_claim 240, G1 6월 합산 3,888,097, 상태 지급완료 196 · 미접수 40 · 반려 4. 05: 일치 쌍 4(관련자 3 · 정황 1), 그룹 G1 하나. 06: 달마다 40건 · 판정 단위 38(단독 35 + G1), 한도 초과는 매달 G1 뿐(1~5월 4,870,186 · 4,540,341 · 4,055,114 · 4,267,112 · 4,505,596 = 22,238,349), 6월 영업임원 3 · 영업지원팀 37, 단독 최대 1,822,391(4월), 개별 최대 1,867,253.

## 다음에 할 일

- 08 커밋 · 푸시 · PR (사용자, Git 명세서 11/12 전달: `git switch -c feat/intake-june-batch` → 코드 커밋 + 메모리 커밋 → `git push -u github feat/intake-june-batch`). 머지 뒤 `git switch main` → `git pull github main`.
- 로드맵 09 `feat/approval-request`(상신 요청 생성 · 역할별 권한 확인 · 승인 / 반려 사유 필수. 완료 기준: 영업지원팀 역할로 상신 건 승인 거부) Step 1.
- 배포 전 `axhub deploy check` 로 원본 COPY 가 들어간 Dockerfile 확인.
- 제출 전 앱 `wake` 후 심사 기간 내내 켜 두기.

## 결정과 근거

- 업무 W07: 판정 규칙이 숫자로 떨어지고 위반 사례(G1)가 데이터에 있음. PwC 감사 · 내부통제와 맞음.
- 스택 FastAPI + SQLite + React(Vite) + LangGraph. FastAPI 하나가 `/api` 와 React 빌드를 함께 서빙(주소 1개). 없는 화면 주소는 index.html, 없는 `/api` 는 404.
- 배포 AXHub lounge · Docker · 앱 이름 `related-party-rebate-agent`(과제 핵심 "관련 거래처"가 이름에 드러나게, 폴더만 짧게). 배포 방식은 생성 후 못 바꿈.
- lounge 는 코드 저장 위치가 Axhub 저장소뿐 → GitHub 원격 이름을 `github` 로 바꾸고 `origin` 을 Axhub 저장소에 넘김(11/11).
- SQLite 는 앱 시작 시 원본 CSV로 다시 만든다(컨테이너 파일은 재배포 · 재시작 때 초기화, 시연 초기화와 같은 동작).
- AI: 판단 · 추천은 AI(LangGraph 그래프 3개: claim_review · explanation_review · master_change_parser), 최종 결정은 사람. AI 는 결재 단계를 올릴 수만 있음(코드 가드). 업무 상태는 DB 한 곳.
- 필수 확장 = 지급 전 미수채권 대조 · 상계 [가정]. 다른 부서 영향 = 재무(채권 회수) · 영업(대리점 관계) · 감사(사후 검토).
- 진행 방식: Step 1→2→3 은 블록으로 받아 대조, **Step 4 에서 Claude 가 정답(메인 · 테스트)을 파일에 반영하고 Git 명세서를 준다**(11/11). 확인 명령은 Step 2 · 3 에 넣지 않고 Step 4 에서 Git 명세서 위에 한 번에(11/12). 사용자는 Step 1 의 브랜치 명령을 바로 치지 않고 Step 4 명세서에서 만든다 → `main` 위면 명세서 ① 에 `git switch -c`(07 · 08). 커밋 · 푸시와 코드를 올리는 axhub 명령은 사용자가 직접.
- 원본 로더: pandas 대신 표준 `csv` + Pydantic(행마다 출처 · 오류 위치 · 빈 값/열 개수 검사, 이미지 크기). `period_ym` 은 문자열, `NONE` 은 None, 틀린 행은 건너뛰지 않고 멈춤. 미수채권은 146행 전부 읽고 대리점 필터는 쓰는 쪽에서.
- 04 DB 범위: 원본 5개 표만(AGENCY · IDENTITY_ATTR · DEPOSIT · AR_ITEM · REBATE_CLAIM), 나머지 표는 처음 쓰는 브랜치에서. DB 는 켤 때마다 새로 만들어 마이그레이션 불필요(11/12).
- AR_ITEM 은 미수채권 146행 전부 저장. `customer_id` 추가, 고객 채권은 `agency_id` 가 비어 있음(11/12).
- REBATE_CLAIM `status` 첫 값: 승인→지급완료, 반려→반려, 미지급→미접수 [가정]. 원본은 `original_status` · `original_approver` · `original_payment_date` 에 보존(11/12).
- IDENTITY_ATTR 초기 182행 = 대리점마다 대표자 · 주소 · 등록계좌 3행(valid_from = registered_date) + 입금마다 실입금계좌 1행(valid_from = deposit_date). valid_from/valid_to 는 date(11/12).
- 상태 · 종류 컬럼은 `StrEnum` + `String` 으로 한글 값을 저장한다. SQLAlchemy `Enum` 은 멤버 이름(`PAID`)을 저장해서 쓰지 않음(11/12).
- 시더는 상태 변환 · 원본 읽기를 `drop_all` 앞에서 끝낸다 → 원본이 틀리면 기존 DB 가 그대로 남는다. 앱은 시작 실패로 드러난다(11/12).
- 로그: `app` 로거만 INFO 로 연다. 루트를 INFO 로 올리면 httpx 요청 로그가 섞인다(SQLAlchemy 는 스스로 WARNING 고정이라 이유가 아님)(11/12).
- `database.py` 는 엔진만. 세션 팩토리 · 요청별 세션 의존성은 처음 조회 API 를 만드는 브랜치에서(뼈대와 다름, 11/12).
- 05 관련자 판정: 계좌는 속성 1개(등록 + 실입금 묶음이 하나라도 겹치면 일치, 따로 세면 공유계좌 하나로 "2개 일치"가 됨). 지금 유효한 속성만, 정확한 문자열 비교. 원본에 공백 · 표기 차이 없음 확인(11/12).
- 05 그룹: 2곳 이상 묶인 것만 저장(단독 47곳은 그룹 없음 → 06 은 자기 금액). 라벨 G1… 은 최소 agency_id 순. 버전 1 은 시더 끝에서 계산 → 초기화 행 수에 표 4개 추가(11/12).
- 05 범위: 엔진 + 표 4개만. API 는 14(건 상세 화면)에서, `REBATE_CLAIM` 그룹 · 결재권자 컬럼은 06, `trigger_change_id` 는 20. 계산(순수 함수)과 저장을 나눠 20 정정 때 재사용(11/12).
- 05 구현: 쌍은 `itertools.combinations` 로 전부 비교(1,225쌍, 규모가 커지면 값 → 대리점 역색인), 전이 묶기는 유니온-파인드. `save_group_version` 은 commit 하지 않음(20 에서 정정과 재계산을 한 트랜잭션으로). 시더 행 수는 `Base.metadata.sorted_tables` 로 DB 에서 센다(11/12).
- 06 한도 판정(B): `REBATE_CLAIM` 에 `min_authority` · `group_id` · `group_sum_krw`(비면 판정 전). 시더는 안 채움 — 대상월 하나를 판정하는 함수가 채우고, 6월분은 08 접수 때. 1~5월을 시작 때 채우면 "판정 당시 그룹" 의미가 깨져서(A 기각). 구성 건은 같은 group_id · 대상월로 조회(11/12).
- 06 규칙: 월 = 대상월 `period_ym`(6월분은 지급일 없음, 지급된 196건은 모두 다음 달 지급이라 결과 같음). 반려 건은 합산 제외(규정 기준이 "지급액"). 2,000,000원 이하 전결 · 초과 영업임원. 지금 버전 그룹 단위, 단독은 자기 금액. 상태는 안 바꿈(07 · 08). 결재권자 역할 enum 은 06 에서(04 docstring 의 "07" 정정). AI 가드 · API 는 범위 밖(17 · 08 · 13)(11/12).
- 07 상태 머신: 상태 14개(미접수 · 접수 · 관계확인 · 전결대기 · 상신대기 · 소명대기 · 지급보류 · 승인 · 반려 · 상계검토 · 지급지시 · 지급완료 · 상계완료 · 재검토필요). 전이표는 dict 데이터(라이브러리 안 씀 — 필요한 게 표 하나, requirements 변경 불필요). 확인 → 변경 → EventLog 를 한 함수에서, commit 안 함. 이유 필수, 같은 상태 전이 금지, 예외 `InvalidTransitionError`(API 409 는 08). 시더는 이력 안 남김(초기화 행 수에 event_log 0). 역할 권한은 09, `actor_role` 은 일단 문자열(11/12).
- 07 전이 결정(사용자 "기본안대로"): 전결대기 → 반려 허용(결재권이 있으면 반려도), 지급보류 → 소명대기 · 지급지시 둘 다(증빙 부족 · 계좌 오류 두 경로), 재검토필요는 돈이 안 나간 9개 상태에서만(지급지시 · 지급완료 · 상계완료 제외, 끝난 건은 감사 24)(11/12).
- 08 접수 흐름: 대상월 건 전부 미접수 → 접수 → `assess_period` → 접수 → 관계확인(payload 에 그룹 · 합산 · 최소 결재권자) → 전결대기 / 상신대기. 요청 하나 = 트랜잭션 하나(`api/deps.py` 의 yield 세션 의존성, 정상이면 commit · 예외면 롤백 — FastAPI 0.141 에서 시험 확인). 세션 팩토리는 안 만듦(`app.state.engine` 사용). 처리자 "시스템"(역할은 12), 정황 작업은 10, AI 검토는 17(11/12).
- 08 결정(사용자 "기본안대로"): 이미 처리한 달 재접수는 상태 머신이 막아 409(별도 검사 없음, 전체 롤백), 건이 없는 달 404, 형식 오류 422(`Query(pattern=…)`). 대상월은 쿼리 `?period=`. 응답은 요약 `{period_ym, received, by_status}`(건 목록은 13). `InvalidTransitionError` → 409 처리기를 `main.py` 에 전역 등록, `ValueError` 전체 → 422 는 안 함(버그를 입력 오류로 가림)(11/12).
- 파이썬 의존성은 leo-dev 설치 버전으로 고정(fastapi 0.141.1, uvicorn 0.52.1) — 로컬과 Docker 동일. 테스트 도구는 `requirements-dev.txt` 로 분리.
- GitHub 이슈는 쓰지 않고 로드맵 번호 · 브랜치 이름으로 관리(1인 · 4일 일정). 저장소 퍼블릭 공개는 주최 측 허용(11/11).
- 루트 `.gitignore`(기록 키 3줄)는 대회 규칙상 수정 금지 → 앱용 ignore 는 폴더별 파일, axhub 로컬 상태 `.axhub/` 는 `.git/info/exclude`.

## 자주 쓰는 원본 사실

- 관련자 그룹 G1 = D-011 · D-024 · D-037 (D-024 실입금계좌 = G1 공유계좌 국민 412-27-556310, DP-00013 · 14 = 원본 14 · 15행). 이 2건이 원본에서 등록계좌와 다른 유일한 입금. 실입금계좌를 빼면 D-024–D-037 은 대표자만 일치(정황)지만 G1 은 전이로 그대로.
- G1 6월분 합산 3,888,097원 → 영업임원 상신 대상. 6월분 40건 `미지급` = 기준일(7/1) 처리할 일.
- 1~5월 G1 15건 22,238,349원이 영업지원팀 전결로 지급됨(한도 200만원 우회).
- G1 미수채권 48,481,080원(120일 넘은 연체 5건). D-034–D-041 은 대표자만 일치 → 정황.
- 원본 행 수: 대리점 50 · 장려금 240(approver NONE 40, payment_date NONE 44) · 입금 32 · 미수채권 146(대리점 74 + 고객 72).
