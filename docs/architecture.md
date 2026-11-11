# W07 판매장려금 통제 데스크 — 설계 다이어그램

> 기준: [W07_설계안.md](W07_설계안.md) v0.1 · 스택 FastAPI + SQLite + React(Vite) + LangChain · 배포 AXHub
> 데이터 출처 표기: **[원본]** 원본 기록 · **[주장]** 부서 주장 · **[가정]** 교육용 가정 · **[모의]** 모의 회신

---

## 1. 시스템 아키텍처

- 배포 단위는 **컨테이너 1개, 주소 1개**다. FastAPI가 `/api`와 React 빌드 결과(`dist`)를 함께 내보낸다.
- **승인 경로는 코드가 정한다.** AI는 해석과 초안만 만들고, 상태는 바꾸지 못한다.
- 원본 CSV는 읽기만 한다. 앱이 켜지거나 초기화할 때 원본으로 SQLite 초기 상태를 다시 만든다.

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
      API["API 라우터<br/>claims · approvals · tasks<br/>agencies · events · demo"]
      subgraph DOMAIN["도메인 서비스 · 결정적 코드"]
        RP["관련자 판정 엔진<br/>2개 이상 일치 · 전이 연결"]
        LR["한도 규칙<br/>그룹 월 합산 200만원"]
        SM["상태 머신<br/>허용된 전이만 통과"]
        TE["작업 엔진<br/>부서별 작업 생성"]
        OF["상계 검토 · 확장<br/>연체 채권 대조"]
      end
      subgraph AIL["AI 계층 · LangChain"]
        CH["체인 3개<br/>승인 요약 · 소명 검토 · 정정 해석"]
        VF["검증기<br/>숫자 대조 · 스키마 검사"]
        GW["LLM 게이트웨이<br/>Claude · OpenAI · 대체 모드"]
      end
      MK["모의 외부<br/>은행 회신 · 대리점 회신"]
      SD["시더<br/>원본 CSV를 초기 상태로"]
    end
    DB[("SQLite<br/>업무 상태 · 이벤트 이력")]
  end

  RAW[/"원본 CSV · 읽기 전용<br/>01_참가자_배포용/04_원본데이터"/]
  EXT[/"확장 데이터 [가정]<br/>backend/data/ext"/]
  LLM(("LLM API<br/>Anthropic · OpenAI"))

  USER --> FE
  FE -- "JSON /api" --> API
  API --> DOMAIN
  API --> AIL
  API --> MK
  CH --> VF
  CH --> GW
  GW --> LLM
  DOMAIN --> DB
  AIL --> DB
  MK --> DB
  RAW --> SD
  EXT --> SD
  SD --> DB
```

---

## 2. 페이지 흐름도

- 같은 화면이라도 역할에 따라 보이는 버튼이 다르다. 예: 상신 건의 승인 버튼은 영업임원에게만 보인다.
- 시연 패널은 외부에서 들어오는 사건(접수, 정정 신고, 모의 회신)을 넣는 곳이다. 그 뒤 처리는 시스템이 한다.

```mermaid
flowchart TD
  START(["앱 접속"]) --> ROLE{"역할 선택"}
  ROLE -->|영업지원팀| INBOX
  ROLE -->|영업임원| INBOX
  ROLE -->|재무| INBOX
  ROLE -->|내부감사| TASKS
  ROLE -->|시연 관리자| DEMO

  INBOX["처리함<br/>역할별 대기 건 · 상태 필터"] --> CLAIM["장려금 건 상세<br/>관련자 근거 · 그룹 합산 · AI 요약 · 출처 배지"]
  CLAIM --> GROUP["관련자 그룹 상세<br/>일치 속성 표 · 그룹 버전 이력"]
  GROUP --> AGENCY["대리점 상세<br/>마스터 · 입금 기록 · 미수채권"]
  CLAIM --> LOG["이벤트 이력<br/>누가 · 언제 · 무엇을 · 왜"]

  CLAIM -->|"전결 · 영업지원팀"| CHECK
  CLAIM -->|"상신 · 영업지원팀"| APPROVAL["승인 요청 상세<br/>영업임원 승인 · 반려"]
  APPROVAL -->|승인| CHECK{"같은 그룹에<br/>연체 채권이 있나"}
  APPROVAL -->|"반려 · 소명 먼저"| EXPL["소명 요청 · 회신<br/>AI 검토 결과 · 사람 확인"]
  EXPL -->|"증빙 충분 · 재상신"| APPROVAL
  EXPL -->|"증빙 부족"| HOLD["지급보류<br/>추가 요청 작업"]

  CHECK -->|있음| OFFSET["상계 검토 · 확장<br/>영업 의견 · 재무 승인 · 대리점 동의"]
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

## 3. AI 워크플로우

- AI가 쓰이는 곳은 세 군데다. **승인 요약**, **소명 검토**, **정정 해석**.
- 모든 AI 출력은 검증기를 거친다. 2번 실패하면 대체 모드(템플릿 응답)로 넘어간다.
- AI 결과는 반드시 사람이 확인한 뒤에만 상태 전이로 이어진다. 모든 AI 호출은 `AI_CALL_LOG`에 남는다.

```mermaid
flowchart TD
  subgraph IN["입력 사건"]
    E1["6월분 장려금 40건 접수 [원본]"]
    E2["소명 회신 · 자유 문장 [모의]"]
    E3["마스터 정정 신고 · 문장"]
  end

  subgraph CODE["코드 · 결정적 · 승인 경로를 정함"]
    C1["관련자 판정<br/>대표자 · 주소 · 등록계좌 · 실입금계좌"]
    C2{"그룹 월 합산<br/>200만원 초과?"}
    C3["상태 전이 · 작업 생성"]
    C4["그룹 재계산 · 새 버전<br/>영향 건에 재검토필요"]
  end

  subgraph AI["AI · 해석과 초안만 · 상태를 바꾸지 않음"]
    A1["승인 요약 체인<br/>근거 · 대안 초안"]
    V1{"숫자가 코드 계산값과<br/>모두 같은가"}
    A2["소명 검토 체인<br/>사유 유형 · 증빙 충족 여부<br/>부족한 증빙 · 추가 요청문"]
    V2{"출력 스키마가<br/>맞는가"}
    A3["정정 해석 체인<br/>대리점 · 속성 · 이전값 · 새값"]
    V3{"대리점과 속성이<br/>실제로 있는가"}
    FB["대체 모드<br/>템플릿 응답 · 사람이 직접 작성"]
  end

  subgraph HUMAN["사람 · 결정"]
    H1["영업임원<br/>승인 · 반려"]
    H2["영업지원팀<br/>AI 검토 결과 확인 · 수정"]
    H3["영업지원팀<br/>정정 내용 확인"]
  end

  E1 --> C1 --> C2
  C2 -->|"아니오 · 전결"| C3
  C2 -->|"예 · 상신"| A1 --> V1
  V1 -->|통과| H1
  V1 -->|"2회 실패"| FB
  H1 --> C3

  E2 --> A2 --> V2
  V2 -->|통과| H2
  V2 -->|"2회 실패"| FB
  H2 --> C3

  E3 --> A3 --> V3
  V3 -->|통과| H3
  V3 -->|"2회 실패"| FB
  H3 --> C4 --> C1

  FB --> HUMAN
```

---

## 4. ERD

- 원본 테이블(`AGENCY`, `DEPOSIT`, `AR_ITEM`, `REBATE_CLAIM`)은 `source_file`, `source_row`로 원본 행까지 추적한다.
- 원본 값은 덮어쓰지 않는다. 상계로 줄어든 채권은 `AR_ADJUSTMENT`에, 정정된 마스터는 `MASTER_CHANGE`와 `IDENTITY_ATTR`의 유효기간으로 남긴다.
- 관련자 그룹은 **버전 단위**로 다시 계산한다. 정정이 들어오면 새 `GROUP_VERSION`이 생기고, 이전 판단의 근거는 그대로 남는다.

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
    datetime valid_from
    datetime valid_to "정정되면 닫힘"
  }
  DEPOSIT {
    string deposit_id PK "DP-nnnnn"
    string agency_id FK
    date deposit_date
    int amount_krw
    string bank_account_no "실입금계좌"
    string matched_ar_id FK
    int source_row
  }
  AR_ITEM {
    string ar_id PK "AR-Dnnnnn"
    string agency_id FK
    date invoice_date
    date due_date
    int amount_krw
    int outstanding_krw "원본 잔액 · 수정 안 함"
    int aging_days
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
    json ai_parsed
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
    int group_id FK
    string agency_id FK
  }
  RELATION_EDGE {
    int edge_id PK
    int group_version_id FK
    string agency_a FK
    string agency_b FK
    json matched_attrs "일치 속성과 근거 행"
    int match_count
    string judgement "관련자 또는 정황"
  }
  REBATE_CLAIM {
    string rebate_id PK "RB-nnnnn"
    string agency_id FK
    string period_ym
    int sales_performance_krw
    int rebate_amount_krw
    string status "상태 다이어그램 참고"
    string route "전결 또는 상신"
    int group_id FK "판정 당시 그룹"
    int group_sum_krw
    string original_status "원본 승인 미지급 반려"
    int source_row
  }
  APPROVAL_REQUEST {
    int request_id PK
    int group_id FK
    string period_ym
    int group_sum_krw
    string approver_role "영업임원"
    string ai_summary
    bool summary_verified
    string decision "승인 반려"
    string reason
    string decided_by
    datetime decided_at
  }
  APPROVAL_ITEM {
    int request_id FK
    string rebate_id FK
  }
  EXPLANATION_REQUEST {
    int exp_id PK
    string rebate_id FK
    json requested_items
    string status
    string ai_draft "추가 요청문 초안"
  }
  EXPLANATION_REPLY {
    int reply_id PK
    int exp_id FK
    string raw_text
    string provenance "모의"
    string ai_reason_type
    bool ai_evidence_ok
    json ai_missing
    string reviewed_by
    string review_result
  }
  OFFSET_PROPOSAL {
    int offset_id PK
    string rebate_id FK
    string ar_id FK
    int offset_amount_krw
    string sales_opinion
    string finance_decision
    string agency_consent "모의"
    string status
  }
  PAYMENT_ORDER {
    int payment_id PK
    string rebate_id FK
    int amount_krw "상계 후 금액"
    string status
    datetime ordered_at
  }
  BANK_REPLY {
    int reply_id PK
    int payment_id FK
    string result "성공 계좌오류"
    string provenance "모의"
    datetime replied_at
  }
  TASK {
    int task_id PK
    string dept "재무 영업지원 감사"
    string task_type
    string ref_type
    string ref_id
    string status "열림 진행 완료"
    int created_by_event FK
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
  AI_CALL_LOG {
    int call_id PK
    int event_id FK
    string chain "승인요약 소명검토 정정해석"
    string model
    json input
    json output
    bool verified
    bool fallback_used
  }

  AGENCY ||--o{ IDENTITY_ATTR : "식별정보"
  AGENCY ||--o{ DEPOSIT : "입금"
  AGENCY ||--o{ AR_ITEM : "미수채권"
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
  EXPLANATION_REQUEST ||--o{ EXPLANATION_REPLY : "회신"
  REBATE_CLAIM ||--o{ OFFSET_PROPOSAL : "상계 제안"
  AR_ITEM ||--o{ OFFSET_PROPOSAL : "상계 대상"
  OFFSET_PROPOSAL ||--o{ AR_ADJUSTMENT : "잔액 조정"
  AR_ITEM ||--o{ AR_ADJUSTMENT : "조정됨"
  REBATE_CLAIM ||--o{ PAYMENT_ORDER : "지급 지시"
  PAYMENT_ORDER ||--o{ BANK_REPLY : "은행 회신"
  EVENT_LOG ||--o{ TASK : "작업 생성"
  EVENT_LOG ||--o{ AI_CALL_LOG : "AI 호출"
```
