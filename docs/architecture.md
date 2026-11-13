# W07 판매장려금 통제 데스크 — 설계 다이어그램 (v0.2)

> 기준: [W07_설계안.md](W07_설계안.md) v0.2 · 스택 FastAPI + SQLite + React(Vite) + LangGraph · 배포 AXHub
> 데이터 출처 표기: **[원본]** 원본 기록 · **[주장]** 부서 주장 · **[가정]** 교육용 가정 · **[모의]** 모의 회신

---

## 1. 시스템 아키텍처

- 배포 단위는 **컨테이너 1개, 주소 1개**다. FastAPI가 `/api`와 React 빌드 결과(`dist`)를 함께 내보낸다.
- **AI가 판단·추천하고 사람이 최종 결정한다.** 단, AI는 결재 단계를 올릴 수만 있고 내릴 수는 없다(가드).
- **업무 상태는 SQLite 업무 DB에만 있다.** LangGraph 체크포인트에는 그래프가 어디까지 진행됐는지만 있다.
- 원본 CSV는 읽기만 한다. 앱이 켜지거나 초기화할 때 원본으로 초기 상태를 다시 만든다.

```mermaid
flowchart LR
  subgraph USER["사용자 · 화면 상단에서 역할 전환"]
    U1["영업지원팀"]
    U2["영업임원"]
    U3["재무"]
    U4["내부감사"]
    U5["시연 관리자"]
  end

  subgraph AXHUB["AXHub · K8s 컨테이너 1개"]
    direction TB
    FE["React SPA<br/>Vite 빌드 결과 dist"]
    subgraph BE["FastAPI"]
      direction TB
      API["API 라우터<br/>claims · approvals · explanations<br/>offsets · tasks · events · demo"]
      subgraph AGENT["AI 에이전트 계층 · LangGraph"]
        RUN["그래프 실행기<br/>thread_id = 대상 건 ID<br/>사람 결정이 오면 재개"]
        GCR["claim_review<br/>장려금 건 검토"]
        GER["explanation_review<br/>소명 검토 에이전트"]
        GMC["master_change_parser<br/>정정 신고 해석"]
        TOOLS["조회 도구<br/>대리점 · 입금 · 미수채권 · 관련자 그룹"]
        GUARD["가드<br/>숫자 대조 · 결재 단계 하한 · 형식"]
        LLMGW["LLM 게이트웨이<br/>Claude · OpenAI · 대체 모드"]
      end
      subgraph DOMAIN["도메인 서비스 · 결정적 코드"]
        RP["관련자 판정<br/>2개 이상 일치 · 전이 연결"]
        AUTH["결재 권한<br/>그룹 월 합산 · 최소 결재권자"]
        SM["상태 머신<br/>허용된 전이만 통과"]
        TE["작업 생성<br/>부서별 작업"]
        OF["상계 검토 · 확장<br/>연체 채권 대조"]
      end
      MK["모의 외부<br/>은행 회신 · 대리점 회신"]
      SD["시더<br/>원본 CSV를 초기 상태로"]
    end
    DB[("SQLite 업무 DB<br/>업무 상태의 유일한 기준")]
    CK[("LangGraph 체크포인트<br/>그래프 진행 위치만")]
  end

  RAW[/"원본 CSV · 읽기 전용<br/>01_참가자_배포용/04_원본데이터"/]
  EXT[/"확장 데이터 [가정]<br/>backend/data/ext"/]
  LLM(("LLM API<br/>Anthropic · OpenAI"))

  USER --> FE
  FE -- "JSON /api" --> API
  API --> RUN
  API --> DOMAIN
  API --> MK
  RUN --> GCR
  RUN --> GER
  RUN --> GMC
  RUN --> CK
  GCR --> TOOLS
  GER --> TOOLS
  GMC --> TOOLS
  GCR --> GUARD
  GER --> GUARD
  GMC --> GUARD
  GCR --> LLMGW
  GER --> LLMGW
  GMC --> LLMGW
  LLMGW --> LLM
  TOOLS --> RP
  GUARD --> AUTH
  RUN -- "사람 결정 뒤 반영" --> SM
  SM --> DB
  TE --> DB
  OF --> DB
  MK --> DB
  TOOLS -. "읽기" .-> DB
  RAW --> SD
  EXT --> SD
  SD --> DB
```

---

## 2. 페이지 흐름도

- 결재권자는 **코드가 계산한 최소 결재권자** 이상이어야 한다. 같은 화면이라도 역할에 따라 보이는 버튼이 다르다.
- 결정 화면마다 **AI 추천 패널**(추천 · 근거 · 반대 근거 · 확신도)이 있다. 추천과 다르게 결정하면 사유를 반드시 입력한다.
- 시연 패널은 외부 사건(접수, 정정 신고, 모의 회신)을 넣는 곳이다. 그 뒤 처리는 시스템이 한다.

```mermaid
flowchart TD
  START(["앱 접속"]) --> ROLE{"역할 선택"}
  ROLE -->|영업지원팀| INBOX
  ROLE -->|영업임원| INBOX
  ROLE -->|재무| INBOX
  ROLE -->|내부감사| TASKS
  ROLE -->|시연 관리자| DEMO

  INBOX["처리함<br/>역할별 대기 건 · 상태 필터"] --> CLAIM["장려금 건 상세<br/>규정 계산 결과 · AI 추천 패널<br/>근거 · 반대 근거 · 출처 배지"]
  CLAIM --> GROUP["관련자 그룹 상세<br/>일치 속성 표 · 그룹 버전 이력"]
  GROUP --> AGENCY["대리점 상세<br/>마스터 · 입금 기록 · 미수채권"]
  CLAIM --> LOG["이벤트 이력<br/>누가 · 언제 · 무엇을 · 왜"]
  LOG --> AIREC["AI 추천 기록<br/>추천과 사람 결정의 일치 여부"]

  CLAIM --> AUTHQ{"최소 결재권자<br/>코드 계산"}
  AUTHQ -->|영업지원팀| SUPP["영업지원팀 결정<br/>AI 추천 참고 · 다르면 사유 필수"]
  AUTHQ -->|영업임원| APPROVAL["승인 요청 상세<br/>AI 추천과 함께 영업임원 결정"]
  SUPP -->|"전결 승인"| CHECK
  SUPP -->|"상신 · AI가 올린 경우 포함"| APPROVAL
  SUPP -->|"소명 먼저"| EXPL
  APPROVAL -->|승인| CHECK{"같은 그룹에<br/>연체 채권이 있나"}
  APPROVAL -->|"반려 · 소명 먼저"| EXPL["소명 요청 · 회신<br/>AI 주장별 대조 결과 · 사람 확인"]
  EXPL -->|"증빙 충분 · 재판정"| AUTHQ
  EXPL -->|"증빙 부족"| HOLD["지급보류<br/>추가 요청 작업"]

  CHECK -->|있음| OFFSET["상계 검토 · 확장<br/>AI 추천 상계액 · 영업 의견<br/>재무 승인 · 대리점 동의"]
  CHECK -->|없음| PAY
  OFFSET -->|"차액 지급"| PAY["지급 지시<br/>모의 은행 회신"]
  OFFSET -->|"전액 상계"| DONE
  PAY --> DONE(["지급완료 · 상계완료"])

  TASKS["부서별 작업 목록<br/>재무 · 영업지원 · 감사"] --> CLAIM
  DEMO["시연 패널<br/>초기화 · 이벤트 넣기"] -->|"6월분 접수"| INBOX
  DEMO -->|"마스터 정정 신고"| GROUP
  DEMO -->|"소명 회신 · 은행 회신"| EXPL
```

---

## 3. AI 워크플로우 (LangGraph)

- 그래프는 3개다. 그래프 1회 실행 = 대상 1개 = thread 1개. thread_id 는 `그래프이름:대상`(16 · 17).
- `claim_review` 의 대상은 **검토 단위**다: 전결 건 하나, 또는 상신 건이면 승인 요청 하나(G1 은 결정 한 번으로 3건이 함께 바뀐다).
- `[[ ]]` 모양은 **interrupt**다. 그래프가 여기서 멈추고, 사람 결정이나 외부 회신이 오면 이어서 실행된다.
- **건 상태는 사람 결정 뒤에만 바뀐다.** `claim_review` 는 결정 API 가 09 서비스로 권한 · 상태를 검사하고 바꾼 뒤, 통과했을 때만 재개한다. LangGraph 는 재개 값을 받는 순간 저장해서, 재개 뒤 노드가 403 · 409 로 실패하면 다음 재개가 그 틀린 값으로 돌기 때문이다(17 에서 시험으로 확인). 그래서 `record_decision` 은 추천 행에 결정 · 일치 여부만 적는다.
- AI가 결재 단계를 최소 결재권자보다 낮게 판단하면 `raise_authority`가 코드 값으로 고정하고 불일치를 기록한다.
- `wait_external` · `apply_reply` 는 22(대리점 동의)에서 더한다. 은행 회신은 11 의 API 로 처리한다.
- `explanation_review` 의 대상은 **소명 회신 하나**다(thread_id `explanation_review:explanation_reply:{reply_id}`). 건 상태와 사람 확인 결과는 확인 API 가 서비스(`services/explanation.py`)로 먼저 적고, 통과했을 때만 그래프를 재개한다(`claim_review` 와 같은 이유). 그래서 `record_decision` 노드가 없고, AI 검토를 건너뛴 확인도 기록이 남는다.
- `check_claim` 은 모델이 도구를 골라 부르는 반복을 직접 돌린다(주장 하나당 최대 4라운드). 도구가 실제로 돌려준 근거 행만 인정하고, 근거 없이 일치 · 불일치를 말하면 코드가 **확인불가로 내린다**. 종합 판단의 증빙 충분은 모든 주장이 일치일 때만 허용하며, 어기면 1회 다시 생성하고 2회 실패하면 대체 모드다.

```mermaid
flowchart TD
  subgraph CR["claim_review · 장려금 건 검토"]
    S1(["시작<br/>접수 · 재검토필요"]) --> N1["load_context · 도구<br/>대리점 · 입금 · 미수채권 · 그룹"]
    N1 --> N2["compute_rules · 코드<br/>관련자 판정 · 그룹 합산<br/>최소 결재권자"]
    N2 --> N3["assess · AI<br/>추천: 전결 · 상신 · 소명 먼저 · 상계 검토<br/>근거 · 반대 근거 · 확신도"]
    N3 --> N4{"verify · 가드<br/>숫자가 계산값과 같은가<br/>결재 단계가 최소 이상인가"}
    N4 -->|"숫자 · 형식 불일치 · 1회차"| N3
    N4 -->|"2회 실패 · 모델 없음"| N5["fallback<br/>AI 추천 없이 규정 결과만"]
    N4 -->|"결재 단계가 낮음"| N6["raise_authority<br/>코드 값으로 고정 · 불일치 기록"]
    N4 -->|통과| NS
    N5 --> NS
    N6 --> NS
    NS["save_recommendation<br/>AI_RECOMMENDATION 저장"] --> N7
    N7[["human_decision · interrupt<br/>AI 추천과 함께 결정 요청"]]
    N7 -->|"결정 API 가 서비스로 상태 변경 뒤 재개"| N8["record_decision<br/>결정 · 추천 일치 여부 기록"]
    N8 --> N9{"후속 처리 (22)"}
    N9 -->|"지급 · 상계"| N10[["wait_external · interrupt<br/>은행 회신 · 대리점 동의"]]
    N10 --> N11["apply_reply<br/>지급완료 · 상계완료 · 지급보류"]
    N11 --> END1(["끝"])
  end

  subgraph ER["explanation_review · 소명 검토 에이전트"]
    E0(["소명 회신 도착 [모의]"]) --> E1["extract_claims · AI<br/>회신 속 주장 목록"]
    E1 -->|"모델 없음 · 추출 실패"| E7["fallback<br/>AI 판단 없이 회신 원문만"]
    E1 --> E2["check_claim · AI + 도구<br/>주장 하나씩 조회 · 대조<br/>근거 행은 도구 결과에 있는 것만 인정"]
    E2 -->|"남은 주장 있음"| E2
    E2 --> E3["assess · AI<br/>증빙 충분 · 부족 · 부족한 증빙 · 추가 요청문"]
    E3 --> E4{"verify · 가드<br/>충분은 모든 주장이 일치일 때만"}
    E4 -->|"문제 · 1회차"| E3
    E4 -->|"2회 실패 · 모델 없음"| E7
    E4 -->|통과| E8["save_review<br/>AI 판단 · 주장별 결과 저장"]
    E7 --> E8
    E8 --> E5[["human_decision · interrupt<br/>영업지원팀 확인"]]
    E5 -->|"증빙 충분 · 소명대기 → 관계확인"| S1
    E5 -->|"증빙 부족 · 소명대기 → 지급보류"| E6["추가 소명 요청 작업"]
  end

  subgraph MC["master_change_parser · 정정 신고 해석"]
    M0(["정정 신고 문장"]) --> M1["parse · AI<br/>대리점 · 속성 · 이전 값 · 새 값"]
    M1 --> M2{"verify · 가드<br/>대리점·속성 존재 · 이전 값 일치"}
    M2 -->|"통과 · 2회 실패 시 직접 입력"| M3[["human_decision · interrupt<br/>영업지원팀 확인"]]
    M3 -->|확정| M4["apply_change · 코드<br/>그룹 재계산 · 새 버전<br/>영향 건에 재검토필요"]
  end

  N9 -->|"소명 먼저"| E0
  M4 -->|"영향 건마다 재실행"| S1
```

---

## 4. ERD

- 원본 테이블(`AGENCY`, `DEPOSIT`, `AR_ITEM`, `REBATE_CLAIM`)은 `source_file`, `source_row`로 원본 행까지 추적한다.
- 원본 값은 덮어쓰지 않는다. 상계로 줄어든 채권은 `AR_ADJUSTMENT`에, 정정된 마스터는 `MASTER_CHANGE`와 `IDENTITY_ATTR`의 유효기간으로 남긴다.
- 관련자 그룹은 **버전 단위**로 다시 계산한다. 정정이 들어오면 새 `GROUP_VERSION`이 생기고, 이전 판단의 근거는 그대로 남는다.
- `AI_RECOMMENDATION`은 AI 추천과 사람의 최종 결정을 한 행에 함께 남긴다. 추천 일치율을 여기서 계산한다.
- LangGraph 체크포인트 테이블은 라이브러리가 관리하므로 ERD에 넣지 않았다.
- **04 `feat/db-schema` 는 원본 5개 표만 만든다**(`AGENCY` · `IDENTITY_ATTR` · `DEPOSIT` · `AR_ITEM` · `REBATE_CLAIM`). 나머지 표는 처음 쓰는 브랜치에서 추가한다. DB 는 켤 때마다 원본으로 새로 만들므로 마이그레이션 도구는 쓰지 않는다.
- `AR_ITEM` 은 원본 146행(대리점 채권 74 + 고객 채권 72)을 전부 저장한다. 고객 채권은 `customer_id` 만 있고 `agency_id` 는 비어 있다.
- `IDENTITY_ATTR` 초기 행 = 대리점마다 대표자 · 주소 · 등록계좌 3행(`valid_from` = `registered_date`) + 입금마다 실입금계좌 1행(`valid_from` = `deposit_date`) = 150 + 32 = 182행.
- `REBATE_CLAIM.status` 첫 값은 원본 상태에서 옮긴다: 승인 → 지급완료, 반려 → 반려, 미지급 → 미접수 **[가정]**. 원본 값은 `original_status` · `original_approver` · `original_payment_date` 에 그대로 남긴다.
- **05 `feat/related-party-engine` 은 관련자 표 4개를 더한다**(`GROUP_VERSION` · `RELATED_GROUP` · `GROUP_MEMBER` · `RELATION_EDGE`). 버전 1 은 앱을 켤 때 시더 끝에서 계산한다. `trigger_change_id` 는 `MASTER_CHANGE` 와 함께 20 에서, `REBATE_CLAIM` 의 `min_authority` · `group_id` · `group_sum_krw` 는 한도 판정을 하는 06 에서 더한다.
- 판정: 대표자 · 주소 · 계좌 중 2개 이상 같으면 관련자, 1개면 정황. **계좌는 속성 1개**로, 대리점의 등록계좌와 실입금계좌를 한 묶음으로 보고 묶음끼리 하나라도 겹치면 일치다. 지금 유효한 속성(`valid_to` 가 비어 있음)만, 문자열이 정확히 같을 때만 일치로 본다.
- `RELATED_GROUP` 은 **2곳 이상 묶인 그룹만** 저장한다(원본 기준 G1 하나). 그룹이 없는 대리점은 자기 금액만으로 한도를 본다. 라벨은 그룹 안 가장 작은 `agency_id` 순으로 G1, G2 … 를 붙인다.
- `RELATION_EDGE` 는 1개 이상 일치한 쌍만 저장한다(원본 기준 4쌍: 관련자 3 · 정황 1). `agency_a` 가 작은 ID 다. `matched_attrs` 는 일치한 속성마다 값과 양쪽 근거 행(`IDENTITY_ATTR.source_ref`)을 담는다.
- **06 `feat/approval-authority` 는 `REBATE_CLAIM` 에 `min_authority` · `group_id` · `group_sum_krw` 를 더한다.** 셋 다 비어 있을 수 있고, 비어 있으면 아직 판정 전이다. 시더는 채우지 않는다. 대상월 하나를 판정하는 함수가 채우며, 6월분은 08 접수 때 채운다(1~5월 위반은 감사 24 에서 같은 함수로 계산).
- 한도 판정: 대상월(`period_ym`) 기준, 지금 버전 그룹 단위(그룹이 없으면 대리점 혼자)로 반려 건을 뺀 장려금을 합산한다. 2,000,000원 이하면 영업지원팀, 넘으면 영업임원. 단독 대리점도 `group_sum_krw` 에 자기 금액을 넣고 `group_id` 는 비운다. 구성 건은 같은 `group_id` · 같은 대상월로 조회하며 따로 저장하지 않는다.
- **09 `feat/approval-request` 는 `APPROVAL_REQUEST` · `APPROVAL_ITEM` 을 더한다.** 08 접수 때 상신대기로 간 건을 판정 단위마다 묶어 요청 1건을 같은 트랜잭션에서 만든다(원본 기준 G1 요청 1건 · 포함 3건). `rec_id` 컬럼은 두지 않는다. 17 의 `AI_RECOMMENDATION` 이 `target_type`(`approval_request`) · `target_id` 로 요청을 가리킨다. 그룹 근거는 복사하지 않고 `group_id` 로 `RELATION_EDGE` 를 찾는다.
- 결재 권한: 결정하는 역할이 요구 역할(요청의 `approver_role`, 전결 건은 `min_authority`) **이상** 이어야 한다(`ApproverRole` 순서로 비교, 결재권자가 아닌 역할은 항상 부족 → 403). 반려는 사유 필수(422). 이미 결정된 요청 · 건은 상태 머신이 막는다(409). 상신대기 건은 전결 결정 길로 결정할 수 없다(요청 기록 없이 승인되는 것을 막음). 결정자 이름 · 역할은 시연용으로 요청 본문에 담는다(실제 시스템이면 로그인 토큰에서 꺼낸다).
- **10 `feat/task-dispatcher` 는 `TASK` 를 더한다.** 작업은 상태 머신의 전이 함수 안에서 규칙표로 자동 생성된다(상태를 바꾸는 길이 하나라 빠지는 작업이 없다). 규칙표 키는 (이전 상태, 이후 상태)이고 이전 상태 조건이 없는 규칙은 "아무거나"다: 승인 → 재무 지급 실행, 소명대기 → 영업지원팀 소명 요청, 소명대기 → 지급보류 → 영업지원팀 추가 소명 요청, 지급지시 → 지급보류 → 재무 지급 계좌 확인, 상계검토 → 재무 상계 검토, 재검토필요 → 영업지원팀 재판정. 결재 대기(전결대기 · 상신대기)는 작업이 아니라 처리함에서 다룬다.
- 건이 어떤 상태를 떠나면 그 상태(`trigger_status`)가 만든 열린 작업은 자동 완료된다(예: 승인 → 지급지시 이면 지급 실행 작업이 닫힘). 사람은 작업 API 로 열림 → 진행 → 완료를 표시하고, 완료는 다시 열 수 없다. 작업 상태 변경은 이력(`EVENT_LOG`)에 남기지 않는다. 상태 전이가 아닌 작업(접수 때 정황 소명 요청 · 24 의 감사 사후 검토)은 `trigger_status` · `created_by_event` 가 비어 있다. 부서 이름은 역할 이름과 같다.
- **18 `feat/explanation-review-graph` 는 `EXPLANATION_REQUEST` · `EXPLANATION_REPLY` · `EXPLANATION_CHECK` 를 더한다.** 요청은 반려 · 지급보류 건에만 만들 수 있고(상신대기 G1 건 하나만 소명대기로 빠지면 3건이 한 묶음인 승인 요청과 어긋난다) 건은 소명대기가 된다. 요청 하나에 회신은 하나(`unique`)이고, 보완 회신은 새 요청으로 받는다. AI 판단(증빙 충분 · 부족)은 `AI_RECOMMENDATION`(승인 · 반려 · 소명 먼저)과 의미가 달라 `EXPLANATION_REPLY` 에 직접 두며, 그래서 `rec_id` 는 없다. 사람 확인 결과도 서비스가 같은 행에 적는다. 증빙 충분이면 소명대기 → 관계확인, 증빙 부족이면 소명대기 → 지급보류.
- **11 `feat/payment-mock` 은 `PAYMENT_ORDER` · `BANK_REPLY` 를 더한다.** 지급 지시는 재무만(403), 승인 건 또는 마지막 지시가 계좌오류였던 지급보류 건만 된다(409 — 증빙 부족으로 보류된 건이 지급되는 것을 막음). 은행 회신은 시연이 결과를 골라 넣는 API 이고 출처는 `모의`, 지시 하나에 회신 하나(두 번째는 409). 성공 → 지급완료, 계좌오류 → 지급보류(재무 계좌 확인 작업) → 다시 지시하면 새 지시를 만든다. 실제 수취계좌는 원본에 없어(설계안 2장) 지급 계좌 컬럼은 두지 않는다. 금액은 22 전까지 장려금액이다.

```mermaid
erDiagram
  AGENCY {
    string agency_id PK "D-001 ~ D-050"
    string agency_name
    string representative_name
    string business_reg_no
    string address
    string bank_account_no "등록 정산계좌"
    bool rebate_eligible
    date registered_date
    string source_file
    int source_row
  }
  IDENTITY_ATTR {
    int id PK
    string agency_id FK
    string attr_type "대표자 주소 등록계좌 실입금계좌"
    string value
    string provenance "원본 가정 모의"
    string source_ref "파일과 행"
    date valid_from
    date valid_to "정정되면 닫힘"
  }
  DEPOSIT {
    string deposit_id PK "DP-nnnnn"
    string agency_id FK
    date deposit_date
    int amount_krw
    string bank_account_no "실입금계좌"
    string matched_ar_id FK
    string source_file
    int source_row
  }
  AR_ITEM {
    string ar_id PK "AR-Dnnnnn"
    string agency_id FK "고객 채권이면 비어 있음"
    string customer_id "고객 채권만"
    date invoice_date
    date due_date
    int amount_krw
    int outstanding_krw "원본 잔액 · 수정 안 함"
    int aging_days
    string source_file
    int source_row
  }
  AR_ADJUSTMENT {
    int id PK
    string ar_id FK
    int offset_id FK
    int amount_krw "상계로 줄어든 금액"
    string provenance "가정"
    datetime applied_at
  }
  MASTER_CHANGE {
    int change_id PK
    string agency_id FK
    string attr_type
    string old_value
    string new_value
    string raw_text "신고 원문"
    string confirmed_by
    datetime applied_at
  }
  GROUP_VERSION {
    int group_version_id PK
    int version_no
    int trigger_change_id FK "없으면 초기 계산"
    bool is_current
    datetime created_at
  }
  RELATED_GROUP {
    int group_id PK
    int group_version_id FK
    string label "G1 등"
  }
  GROUP_MEMBER {
    int group_id PK, FK
    string agency_id PK, FK
  }
  RELATION_EDGE {
    int edge_id PK
    int group_version_id FK
    string agency_a FK "작은 ID"
    string agency_b FK
    json matched_attrs "속성마다 값과 양쪽 근거 행"
    int match_count
    string judgement "관련자 또는 정황"
  }
  REBATE_CLAIM {
    string rebate_id PK "RB-nnnnn"
    string agency_id FK
    string period_ym
    int sales_performance_krw
    int rebate_amount_krw
    string status "업무 상태 · 유일한 기준"
    string min_authority "코드 계산 최소 결재권자 · 비면 판정 전"
    int group_id FK "판정 당시 그룹 · 단독이면 비어 있음"
    int group_sum_krw "판정 단위 월 합산"
    string original_status "원본 승인 미지급 반려"
    string original_approver "원본 · NONE 이면 비어 있음"
    date original_payment_date "원본 · NONE 이면 비어 있음"
    string source_file
    int source_row
  }
  APPROVAL_REQUEST {
    int request_id PK
    int group_id FK "단독 대리점이면 비어 있음"
    string period_ym
    int group_sum_krw
    string approver_role "영업임원"
    int rec_id FK "AI 추천 · 17 에서"
    datetime created_at
    string decision "승인 반려 · 결정 전엔 비어 있음"
    string reason
    string decided_by
    datetime decided_at
  }
  APPROVAL_ITEM {
    int request_id PK, FK
    string rebate_id PK, FK
  }
  EXPLANATION_REQUEST {
    int exp_id PK
    string rebate_id FK
    json requested_items
    string status "회신대기 회신됨 확인완료"
    string requested_by
    datetime created_at
  }
  EXPLANATION_REPLY {
    int reply_id PK
    int exp_id FK "unique · 요청 하나에 회신 하나"
    string raw_text
    string provenance "모의"
    string ai_judgement "증빙 충분 증빙 부족 · 대체 모드면 비어 있음"
    json ai_rationale
    json missing_evidence
    string follow_up_request
    float ai_confidence
    bool verified
    bool fallback_used
    string model
    string review_result "사람 확인 결과"
    string review_reason
    string reviewed_by
    datetime reviewed_at
    bool agreed "AI 판단과 같은가"
    datetime created_at
  }
  EXPLANATION_CHECK {
    int check_id PK
    int reply_id FK
    int seq
    string claim_text "회신 속 주장"
    string verdict "일치 불일치 확인불가"
    string finding
    json tool_used
    json evidence_ref "도구가 돌려준 원본 행"
  }
  OFFSET_PROPOSAL {
    int offset_id PK
    string rebate_id FK
    string ar_id FK
    int offset_amount_krw
    int rec_id FK "AI 추천 상계액"
    string sales_opinion
    string finance_decision
    string agency_consent "모의"
    string status
  }
  PAYMENT_ORDER {
    int payment_id PK
    string rebate_id FK
    int amount_krw "상계 후 금액 · 22 전까지는 장려금액"
    string status "회신대기 성공 계좌오류"
    string ordered_by
    datetime ordered_at
  }
  BANK_REPLY {
    int reply_id PK
    int payment_id FK "지시 하나에 회신 하나"
    string result "성공 계좌오류"
    string provenance "모의"
    datetime replied_at
  }
  AI_RECOMMENDATION {
    int rec_id PK
    string graph "claim_review 등"
    string thread_id "그래프이름:대상"
    string target_type
    string target_id
    string recommendation
    json rationale "근거와 원본 행"
    json counter_evidence
    float confidence
    string min_authority "코드 계산"
    string ai_authority "AI 판단"
    bool authority_raised "AI가 낮게 판단해 고정됨"
    bool verified
    bool fallback_used
    string model
    string human_decision
    string human_reason "추천과 다르면 필수"
    bool agreed
    string decided_by
    datetime decided_at
  }
  TASK {
    int task_id PK
    string dept "재무 영업지원팀 내부감사"
    string task_type
    string ref_type
    string ref_id
    string status "열림 진행 완료"
    string trigger_status "이 작업을 만든 상태 · 전이 아니면 비어 있음"
    string detail "생긴 이유"
    int created_by_event FK "전이 아니면 비어 있음"
    datetime created_at
    datetime closed_at
  }
  EVENT_LOG {
    int event_id PK
    datetime ts
    string actor
    string actor_role
    string entity_type
    string entity_id
    string from_status
    string to_status
    string reason
    json payload
  }

  AGENCY ||--o{ IDENTITY_ATTR : "식별정보"
  AGENCY ||--o{ DEPOSIT : "입금"
  AGENCY |o--o{ AR_ITEM : "미수채권"
  AGENCY ||--o{ REBATE_CLAIM : "장려금"
  AGENCY ||--o{ MASTER_CHANGE : "정정 신고"
  AGENCY ||--o{ GROUP_MEMBER : "소속"
  AGENCY ||--o{ RELATION_EDGE : "관계 A"
  AGENCY ||--o{ RELATION_EDGE : "관계 B"
  DEPOSIT }o--o| AR_ITEM : "대사"
  MASTER_CHANGE ||--o| GROUP_VERSION : "재계산 계기"
  GROUP_VERSION ||--o{ RELATED_GROUP : "포함"
  GROUP_VERSION ||--o{ RELATION_EDGE : "계산 결과"
  RELATED_GROUP ||--|{ GROUP_MEMBER : "구성원"
  RELATED_GROUP ||--o{ REBATE_CLAIM : "합산 단위"
  RELATED_GROUP ||--o{ APPROVAL_REQUEST : "상신 단위"
  APPROVAL_REQUEST ||--|{ APPROVAL_ITEM : "포함 건"
  REBATE_CLAIM ||--o{ APPROVAL_ITEM : "상신됨"
  REBATE_CLAIM ||--o{ EXPLANATION_REQUEST : "소명 요청"
  EXPLANATION_REQUEST ||--o| EXPLANATION_REPLY : "회신"
  EXPLANATION_REPLY ||--o{ EXPLANATION_CHECK : "주장 대조"
  REBATE_CLAIM ||--o{ OFFSET_PROPOSAL : "상계 제안"
  AR_ITEM ||--o{ OFFSET_PROPOSAL : "상계 대상"
  OFFSET_PROPOSAL ||--o{ AR_ADJUSTMENT : "잔액 조정"
  AR_ITEM ||--o{ AR_ADJUSTMENT : "조정됨"
  REBATE_CLAIM ||--o{ PAYMENT_ORDER : "지급 지시"
  PAYMENT_ORDER ||--o{ BANK_REPLY : "은행 회신"
  REBATE_CLAIM ||--o{ AI_RECOMMENDATION : "검토 이력"
  AI_RECOMMENDATION ||--o| APPROVAL_REQUEST : "상신 근거"
  AI_RECOMMENDATION ||--o| OFFSET_PROPOSAL : "상계 추천"
  EVENT_LOG ||--o{ TASK : "작업 생성"
```

---

## 5. 장려금 건 상태 전이

- 상태는 `REBATE_CLAIM.status` 한 곳에만 있고, 바꾸는 길은 `services/claim_state.py` 하나다. 허용 여부 확인 → 상태 변경 → `EVENT_LOG` 한 줄이 한 함수에서 함께 일어난다(07).
- 전이표는 코드에서 데이터(상태 → 갈 수 있는 상태들)로 두고, 이 그림은 그 표와 같다. 허용되지 않은 전이와 같은 상태로의 전이는 막고, 이유는 모든 전이에서 필수다.
- 원본에서 옮긴 첫 상태(미접수 · 지급완료 · 반려)는 전이가 아니라서 이력을 남기지 않는다.
- 재검토필요는 아직 돈이 나가지 않은 9개 상태에서만 들어온다. 지급지시는 은행에 보낸 지시를 되돌릴 수 없어서, 지급완료 · 상계완료는 끝난 건이라 빠진다(끝난 건은 감사 사후 검토 작업으로 다룬다).
- 역할 권한(누가 어떤 전이를 할 수 있나)은 09 에서 전이 함수 앞에 둔다. 상태 머신은 누가 했는지 기록만 한다.

```mermaid
stateDiagram-v2
  [*] --> 미접수 : 원본 미지급 [가정]
  미접수 --> 접수 : 6월분 접수(08)
  접수 --> 관계확인 : 관련자 · 한도 판정
  관계확인 --> 전결대기 : 최소 결재권자 영업지원팀
  관계확인 --> 상신대기 : 최소 결재권자 영업임원
  관계확인 --> 소명대기 : 소명 먼저
  전결대기 --> 승인 : 전결 승인
  전결대기 --> 반려 : 전결 반려
  전결대기 --> 상신대기 : 상신(AI가 올린 경우 포함)
  전결대기 --> 소명대기 : 소명 먼저
  상신대기 --> 승인 : 영업임원 승인
  상신대기 --> 반려 : 영업임원 반려
  상신대기 --> 소명대기 : 소명 먼저
  반려 --> 소명대기 : 소명 요청(21)
  소명대기 --> 관계확인 : 증빙 충분 · 재판정
  소명대기 --> 지급보류 : 증빙 부족
  지급보류 --> 소명대기 : 추가 소명 요청
  지급보류 --> 지급지시 : 계좌 확인 뒤 재지시
  승인 --> 상계검토 : 같은 그룹 연체 채권 [가정]
  승인 --> 지급지시 : 연체 채권 없음
  상계검토 --> 지급지시 : 차액 지급
  상계검토 --> 상계완료 : 전액 상계
  지급지시 --> 지급완료 : 은행 회신 성공 [모의]
  지급지시 --> 지급보류 : 은행 회신 계좌 오류 [모의]
  재검토필요 --> 관계확인 : 다시 판정
  지급완료 --> [*]
  상계완료 --> [*]
```

재검토필요로 들어오는 전이(마스터 정정 · 그룹 버전 변경, 20)는 그림이 복잡해져 화살표 대신 목록으로 적는다: 접수 · 관계확인 · 전결대기 · 상신대기 · 소명대기 · 지급보류 · 승인 · 반려 · 상계검토 → 재검토필요.
