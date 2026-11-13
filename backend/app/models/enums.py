"""업무 코드 값.

DB 에는 한글 값 그대로 문자열로 저장한다. StrEnum 은 문자열과 같게 비교되므로
String 컬럼에 그대로 넣고 꺼내도 된다.
"""

from enum import StrEnum


class Provenance(StrEnum):
    """데이터 출처 표기."""

    ORIGINAL = "원본"
    CLAIMED = "주장"
    ASSUMED = "가정"
    MOCK = "모의"


class IdentityAttrType(StrEnum):
    """관련자 판정에 쓰는 식별속성 종류."""

    REPRESENTATIVE = "대표자"
    ADDRESS = "주소"
    REGISTERED_ACCOUNT = "등록계좌"
    DEPOSIT_ACCOUNT = "실입금계좌"


class ClaimStatus(StrEnum):
    """장려금 건 업무 상태. 업무 흐름 순서로 적는다.

    바꾸는 길은 services/claim_state.py 하나다. 허용되는 전이는 docs/architecture.md 5장.
    """

    NOT_RECEIVED = "미접수"
    RECEIVED = "접수"
    RELATION_CHECKED = "관계확인"
    AWAITING_SUPPORT = "전결대기"
    AWAITING_EXECUTIVE = "상신대기"
    AWAITING_EXPLANATION = "소명대기"
    ON_HOLD = "지급보류"
    APPROVED = "승인"
    REJECTED = "반려"
    OFFSET_REVIEW = "상계검토"
    PAYMENT_ORDERED = "지급지시"
    PAID = "지급완료"
    OFFSET_DONE = "상계완료"
    NEEDS_REVIEW = "재검토필요"


class ApproverRole(StrEnum):
    """장려금 결재권자. 낮은 단계부터 적는다."""

    SALES_SUPPORT = "영업지원팀"
    SALES_EXECUTIVE = "영업임원"


class Decision(StrEnum):
    """결재권자가 고르는 결정. 건의 상태(ClaimStatus)와 글자는 같아도 뜻이 다르다."""

    APPROVE = "승인"
    REJECT = "반려"


class Department(StrEnum):
    """작업을 받는 부서. 역할 이름과 같게 써서 역할 화면에서 그대로 거른다."""

    FINANCE = "재무"
    SALES_SUPPORT = "영업지원팀"
    AUDIT = "내부감사"


class TaskStatus(StrEnum):
    """부서별 작업 상태. 열림에서 바로 완료로 갈 수도 있다."""

    OPEN = "열림"
    IN_PROGRESS = "진행"
    DONE = "완료"


class PaymentStatus(StrEnum):
    """지급 지시 상태. 회신을 받으면 은행 회신 결과와 같은 값이 된다."""

    AWAITING_REPLY = "회신대기"
    SUCCEEDED = "성공"
    ACCOUNT_ERROR = "계좌오류"


class BankResult(StrEnum):
    """은행 회신 결과 [모의]. 회신대기는 결과가 아니라서 넣지 않는다."""

    SUCCESS = "성공"
    ACCOUNT_ERROR = "계좌오류"


class MatchAttr(StrEnum):
    """관련자 판정에 세는 속성. 등록계좌와 실입금계좌는 '계좌' 하나로 센다."""

    REPRESENTATIVE = "대표자"
    ADDRESS = "주소"
    ACCOUNT = "계좌"


class RelationJudgement(StrEnum):
    """두 대리점 사이 판정. 2개 이상 일치는 관련자, 1개 일치는 정황."""

    RELATED = "관련자"
    CIRCUMSTANTIAL = "정황"


class Recommendation(StrEnum):
    """AI 가 내는 추천. 사람은 승인 · 반려만 고른다(소명 먼저는 21 전까지 추천으로만 남는다)."""

    APPROVE = "승인"
    REJECT = "반려"
    EXPLAIN_FIRST = "소명 먼저"


class ExplanationStatus(StrEnum):
    """소명 요청 한 건의 진행 상태. 요청 하나에 회신은 하나다."""

    AWAITING_REPLY = "회신대기"
    REPLIED = "회신됨"
    CONFIRMED = "확인완료"
    # 정정 신고로 건이 재검토필요로 돌아가 더는 받을 회신이 없을 때
    CANCELLED = "취소"


class CheckVerdict(StrEnum):
    """회신 속 주장 하나를 데이터와 대조한 결과. 건(claim)과 헷갈리지 않게 Check 로 쓴다."""

    CONSISTENT = "일치"
    INCONSISTENT = "불일치"
    UNVERIFIABLE = "확인불가"


class ExplanationJudgement(StrEnum):
    """소명이 충분한지의 판단. AI 판단과 영업지원팀 확인 결과가 같은 값을 쓴다."""

    SUFFICIENT = "증빙 충분"
    INSUFFICIENT = "증빙 부족"


class OffsetStatus(StrEnum):
    """상계 제안 한 건의 진행 상태 [가정]. 재무검토 · 동의대기 가 열린 상태다."""

    AWAITING_FINANCE = "재무검토"
    AWAITING_CONSENT = "동의대기"
    SETTLED = "상계확정"
    # 재무가 상계하지 않기로 함 → 전액 지급
    FINANCE_REJECTED = "재무반려"
    # 대리점이 동의하지 않음 → 상계할 수 없어 전액 지급
    CONSENT_REFUSED = "동의거절"
    # 정정 신고로 건이 재검토필요로 돌아가 판정 단위가 바뀜(20)
    CANCELLED = "취소"


class AgencyConsent(StrEnum):
    """상계에 대한 대리점 회신 [모의]."""

    CONSENT = "동의"
    REFUSE = "거절"


class SalesAlternative(StrEnum):
    """상계 제안에 대한 영업 의견의 대안 [가정]. 대리점 관계 부담을 보고 영업이 고른다."""

    FULL_OFFSET = "전액 상계"
    PARTIAL_OFFSET = "부분 상계"
    # 상계하지 않고 장려금은 지급하되, 대리점에게 연체 채권 회수 약정을 받는다
    PAY_WITH_PLAN = "지급 후 회수 약정"
