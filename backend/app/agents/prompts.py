"""그래프 노드가 쓰는 프롬프트. 지금은 장려금 검토(claim_review)만 있다.

사실(원본 데이터)은 지시문과 섞지 않고 JSON 으로 따로 넣는다.
대리점 이름 같은 원본 문자열이 지시처럼 읽히지 않게 하려는 것이다.
"""

import json
from typing import Any

CLAIM_REVIEW_SYSTEM = """\
당신은 판매장려금 지급 결재를 돕는 검토 보조입니다. 최종 결정은 사람 결재권자가 합니다.

규칙:
- 장려금 한도는 대리점 한 곳이 아니라 판정 단위(관련자 그룹이면 그룹 전체)의 같은 달 합산 기준입니다.
- 합산이 한도 이하이면 영업지원팀 전결, 넘으면 영업임원 결재입니다.
- 관련자 그룹은 대표자 · 주소 · 계좌 중 2개 이상이 같은 대리점끼리 묶은 것입니다.
  1개만 같으면 정황이며 그룹이 아닙니다.
- group_sum_krw 는 사실에 주어진 판정 단위 합산을 그대로 옮기세요. 다시 계산하지 마세요.
- 근거 문장에 데이터 사실을 쓸 때는 끝에 근거 행(파일:행)을 붙이세요.
- 사실에 없는 내용을 지어내지 마세요. 확인이 필요한 점은 반대 근거에 쓰고 확신도를 낮추세요.
"""


def claim_review_messages(
    facts: dict[str, Any], problems: list[str] | None = None
) -> list[tuple[str, str]]:
    """시스템 지시 + 사실(JSON). 이전 답이 가드에 걸렸으면 그 문제를 알려 다시 쓰게 한다."""
    messages = [
        ("system", CLAIM_REVIEW_SYSTEM),
        (
            "human",
            "아래 사실(JSON)만 근거로 이 장려금 건을 검토하세요.\n"
            + json.dumps(facts, ensure_ascii=False, indent=2),
        ),
    ]
    if problems:
        messages.append(
            (
                "human",
                "이전 답에 문제가 있었습니다. 고쳐서 다시 답하세요:\n- "
                + "\n- ".join(problems),
            )
        )
    return messages
