"""소명 표 3개 모델 테스트: 표 생성, 기본값, JSON 목록 저장, 요청 하나에 회신 하나."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ExplanationCheck, ExplanationReply, ExplanationRequest
from app.models.enums import (
    CheckVerdict,
    ExplanationJudgement,
    ExplanationStatus,
    Provenance,
)


def make_request(session, rebate_id="RB-00006") -> ExplanationRequest:
    request = ExplanationRequest(
        rebate_id=rebate_id,
        requested_items=["계좌 공유 사유", "입금 대행 계약서"],
        status=ExplanationStatus.AWAITING_REPLY,
        requested_by="김지원",
    )
    session.add(request)
    session.flush()
    return request


def test_values_are_korean_strings():
    assert ExplanationStatus.REPLIED == "회신됨"
    assert CheckVerdict.INCONSISTENT == "불일치"
    assert ExplanationJudgement.INSUFFICIENT == "증빙 부족"


def test_request_stores_item_list_and_server_time(seeded_engine):
    with Session(seeded_engine) as session, session.begin():
        request = make_request(session)
        session.refresh(request)
        assert request.requested_items == ["계좌 공유 사유", "입금 대행 계약서"]
        assert request.created_at is not None


def test_reply_defaults_are_empty_before_review(seeded_engine):
    """검토 전 회신: AI 판단 · 사람 확인이 모두 비어 있고 목록은 빈 목록이다."""
    with Session(seeded_engine) as session, session.begin():
        request = make_request(session)
        reply = ExplanationReply(
            exp_id=request.exp_id,
            raw_text="세무대리인이 대신 입금",
            provenance=Provenance.MOCK,
        )
        session.add(reply)
        session.flush()
        session.refresh(reply)
        assert reply.ai_judgement is None
        assert reply.ai_rationale == [] and reply.missing_evidence == []
        assert (reply.verified, reply.fallback_used) == (False, False)
        assert reply.review_result is None and reply.agreed is None


def test_one_reply_per_request_is_enforced_by_db(seeded_engine):
    """서비스 검사를 거치지 않아도 DB 가 같은 요청의 두 번째 회신을 막는다."""
    with Session(seeded_engine) as session:
        request = make_request(session)
        for text in ("첫 회신", "둘째 회신"):
            session.add(
                ExplanationReply(
                    exp_id=request.exp_id, raw_text=text, provenance=Provenance.MOCK
                )
            )
        with pytest.raises(IntegrityError):
            session.flush()


def test_check_keeps_tools_and_evidence_lists(seeded_engine):
    with Session(seeded_engine) as session, session.begin():
        request = make_request(session)
        reply = ExplanationReply(
            exp_id=request.exp_id, raw_text="회신", provenance=Provenance.MOCK
        )
        session.add(reply)
        session.flush()
        session.add(
            ExplanationCheck(
                reply_id=reply.reply_id,
                seq=1,
                claim_text="세무대리인이 대신 입금했다",
                verdict=CheckVerdict.INCONSISTENT,
                finding="입금 계좌는 D-011 등록계좌",
                tool_used=["list_deposits", "find_agencies_by_account"],
                evidence_ref=["fin_collection_history_cv.csv:14"],
            )
        )
        session.flush()
        check = session.scalar(select(ExplanationCheck))
        assert check.verdict == "불일치"
        assert check.tool_used == ["list_deposits", "find_agencies_by_account"]
        assert check.evidence_ref == ["fin_collection_history_cv.csv:14"]
