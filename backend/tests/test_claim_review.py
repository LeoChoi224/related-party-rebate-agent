"""claim_review 그래프 테스트.

원본으로 채운 DB 에 6월분을 접수한 뒤, 가짜 모델로 그래프를 사람 결정 앞까지 돌린다.
LLM 호출 없이 가드 · 다시 생성 · 대체 모드 · 결재 단계 올림 · 결정 기록을 본다.
"""

import pytest
from sqlalchemy.orm import Session

from app.agents.checkpointer import make_checkpointer
from app.agents.graphs.claim_review import (
    build_claim_review,
    record_human_decision,
    start_claim_review,
)
from app.agents.runner import InvalidRunStateError, pending_interrupts
from app.models import AIRecommendation, RebateClaim
from app.models.enums import Decision
from app.services.approval import decide_approval, decide_claim
from app.services.intake import intake_period

G1_SUM = 3_888_097
STANDALONE = "RB-00006"


def answer(**overrides) -> dict:
    values = {
        "recommendation": "승인",
        "ai_authority": "영업임원",
        "group_sum_krw": G1_SUM,
        "rationale": ["G1 합산 3,888,097원이 한도를 넘음 (rebate.csv:54)"],
        "counter_evidence": [],
        "confidence": 0.8,
    }
    return values | overrides


@pytest.fixture
def june(seeded_engine):
    with Session(seeded_engine) as session, session.begin():
        intake_period(session, "2026-06")
    return seeded_engine


@pytest.fixture
def checkpointer():
    return make_checkpointer()


def review(engine, checkpointer, model, rebate_id) -> dict:
    """검토를 돌리고 저장된 추천 행을 dict 로 돌려준다(세션 밖에서도 읽게)."""
    with Session(engine) as session, session.begin():
        rec = start_claim_review(session, checkpointer, model, rebate_id)
        return {c.name: getattr(rec, c.name) for c in AIRecommendation.__table__.c}


def standalone_sum(engine) -> int:
    with Session(engine) as session:
        return session.get(RebateClaim, STANDALONE).group_sum_krw


def test_standalone_claim_saves_verified_recommendation(june, checkpointer, fake_model):
    """전결 건: 가드를 통과한 추천이 건 단위로 저장되고, 사람 결정을 기다린다."""
    model = fake_model(
        answer(ai_authority="영업지원팀", group_sum_krw=standalone_sum(june))
    )
    rec = review(june, checkpointer, model, STANDALONE)
    assert (rec["target_type"], rec["target_id"]) == ("rebate_claim", STANDALONE)
    assert rec["thread_id"] == f"claim_review:rebate_claim:{STANDALONE}"
    assert rec["recommendation"] == "승인"
    assert rec["min_authority"] == rec["ai_authority"] == "영업지원팀"
    assert rec["verified"] and not rec["authority_raised"] and not rec["fallback_used"]
    assert rec["model"] == "fake-review"
    graph = build_claim_review(checkpointer)
    key = f"rebate_claim:{STANDALONE}"
    assert pending_interrupts(graph, key) == [{"rec_id": rec["rec_id"]}]


def test_g1_recommended_as_support_is_raised_to_executive(
    june, checkpointer, fake_model
):
    """완료 기준: AI 가 G1 을 전결(영업지원팀)로 추천해도 영업임원으로 고정되고 불일치가 남는다."""
    model = fake_model(answer(ai_authority="영업지원팀"))
    rec = review(june, checkpointer, model, "RB-00054")
    assert rec["target_type"] == "approval_request"
    assert rec["min_authority"] == "영업임원"
    assert rec["ai_authority"] == "영업지원팀"
    assert rec["authority_raised"]
    assert rec["verified"]
    # 사실에 G1 합산과 구성 3건이 들어갔다.
    facts = model.calls[0][1][1]
    assert "3888097" in facts and "RB-00180" in facts


def test_wrong_sum_once_is_regenerated(june, checkpointer, fake_model):
    model = fake_model(answer(group_sum_krw=1_000_000), answer())
    rec = review(june, checkpointer, model, "RB-00054")
    assert len(model.calls) == 2
    # 두 번째 요청에 가드가 찾은 문제를 알려 준다.
    assert "1,000,000원이 코드 계산 3,888,097원과 다릅니다" in model.calls[1][-1][1]
    assert rec["verified"] and not rec["fallback_used"]


def test_wrong_twice_falls_back_without_recommendation(june, checkpointer, fake_model):
    model = fake_model(answer(group_sum_krw=1), answer(group_sum_krw=2))
    rec = review(june, checkpointer, model, "RB-00054")
    assert len(model.calls) == 2
    assert rec["fallback_used"] and not rec["verified"]
    assert rec["recommendation"] is None and rec["rationale"] == []
    assert rec["model"] is None
    # 대체 모드여도 코드 결재권자는 남는다(규정 결과만).
    assert rec["min_authority"] == "영업임원"


def test_no_model_is_fallback_without_calls(june, checkpointer):
    rec = review(june, checkpointer, None, "RB-00054")
    assert rec["fallback_used"] and rec["recommendation"] is None


def test_llm_error_counts_as_one_failed_attempt(june, checkpointer, fake_model):
    model = fake_model(TimeoutError("read timed out"), answer())
    rec = review(june, checkpointer, model, "RB-00054")
    assert len(model.calls) == 2
    assert rec["verified"]


def test_only_waiting_claims_can_be_reviewed(june, checkpointer):
    with Session(june) as session:
        with pytest.raises(LookupError, match="RB-99999"):
            start_claim_review(session, checkpointer, None, "RB-99999")
        # 1월분은 지급완료라 결정할 것이 없다.
        with pytest.raises(InvalidRunStateError, match="지급완료"):
            start_claim_review(session, checkpointer, None, "RB-00049")


def test_g1_members_share_one_review(june, checkpointer):
    """G1 의 다른 건으로 다시 검토하면 같은 승인 요청 스레드라 막힌다."""
    review(june, checkpointer, None, "RB-00054")
    with (
        Session(june) as session,
        pytest.raises(InvalidRunStateError, match="이미 사람 결정을 기다리고"),
    ):
        start_claim_review(session, checkpointer, None, "RB-00120")


def test_decision_is_recorded_with_agreement(june, checkpointer, fake_model):
    """서비스로 결정한 뒤 재개하면 추천 행에 결정과 일치 여부가 남고 검토가 끝난다."""
    rec = review(june, checkpointer, fake_model(answer()), "RB-00054")
    request_id = int(rec["target_id"])
    with Session(june) as session, session.begin():
        decide_approval(
            session,
            request_id,
            decision=Decision.APPROVE,
            reason="",
            actor="박임원",
            role="영업임원",
        )
        assert record_human_decision(
            session,
            checkpointer,
            "approval_request",
            str(request_id),
            decision=Decision.APPROVE,
            reason="",
            actor="박임원",
        )
    with Session(june) as session:
        saved = session.get(AIRecommendation, rec["rec_id"])
        assert (saved.human_decision, saved.decided_by) == ("승인", "박임원")
        assert saved.agreed is True and saved.decided_at is not None
    graph = build_claim_review(checkpointer)
    assert pending_interrupts(graph, f"approval_request:{request_id}") == []


def test_fallback_decision_has_no_agreement(june, checkpointer):
    rec = review(june, checkpointer, None, STANDALONE)
    with Session(june) as session, session.begin():
        decide_claim(
            session,
            STANDALONE,
            decision=Decision.REJECT,
            reason="증빙 확인 필요",
            actor="김지원",
            role="영업지원팀",
        )
        record_human_decision(
            session,
            checkpointer,
            "rebate_claim",
            STANDALONE,
            decision=Decision.REJECT,
            reason="증빙 확인 필요",
            actor="김지원",
        )
    with Session(june) as session:
        saved = session.get(AIRecommendation, rec["rec_id"])
        assert saved.human_decision == "반려"
        assert saved.human_reason == "증빙 확인 필요"
        assert saved.agreed is None


def test_decision_without_review_does_nothing(june, checkpointer):
    with Session(june) as session:
        assert not record_human_decision(
            session,
            checkpointer,
            "rebate_claim",
            STANDALONE,
            decision=Decision.APPROVE,
            reason="",
            actor="김지원",
        )
