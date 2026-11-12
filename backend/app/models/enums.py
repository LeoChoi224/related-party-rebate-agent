"""업무 코드 값.

DB 에는 한글 값 그대로 문자열로 저장한다. StrEnum 은 문자열과 같게 비교되므로
String 컬럼에 그대로 넣고 꺼내도 된다.
장려금 건의 나머지 상태와 결재권자 역할은 07(상태 머신)에서, 관련자 판정 값은 05 에서 더한다.
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
    """장려금 건 업무 상태. 지금은 원본에서 옮긴 첫 값 3개만 둔다."""

    NOT_RECEIVED = "미접수"
    PAID = "지급완료"
    REJECTED = "반려"
