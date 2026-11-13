"""explanation_review 그래프 테스트.

원본으로 채운 DB 에 소명 요청 · 회신 행을 직접 넣고, 가짜 모델로 그래프를 사람 확인 앞까지 돌린다.
LLM 호출 없이 도구 조회 · 근거 가드 · 다시 생성 · 대체 모드 · 도구 오류 · 조회 상한을 본다.
"""

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.checkpointer import make_checkpointer
from app.agents.graphs.explanation_review import (
    MAX_TOOL_STEPS,
    build_explanation_review,
    record_human_confirmation,
    start_explanation_review,
)
from app.agents.runner import InvalidRunStateError, pending_interrupts
from app.agents.tools import collect_refs, find_agencies_by_account
from app.models import (
    ExplanationCheck,
    ExplanationReply,
    ExplanationRequest,
    RebateClaim,
)
from app.models.enums import ExplanationJudgement, ExplanationStatus, Provenance

G1_ACCOUNT = "국민 412-27-556310"
REPLY_TEXT = "D-024는 별도 법인이고, 계좌가 겹친 건 세무대리인이 대신 입금해서입니다."
CLAIM_TEXT = "계좌가 겹친 건 세무대리인이 대신 입금해서이다"


@pytest.fixture
def checkpointer():
    return make_checkpointer()


@pytest.fixture
def reply_id(seeded_engine):
    """D-024 의 6월 건에 달린 회신 한 건(요청 상태 회신됨)."""
    with Session(seeded_engine) as session, session.begin():
        claim = session.scalar(
            select(RebateClaim).where(
                RebateClaim.agency_id == "D-024", RebateClaim.period_ym == "2026-06"
            )
        )
        request = ExplanationRequest(
            rebate_id=claim.rebate_id,
            requested_items=["계좌 공유 사유"],
            status=ExplanationStatus.REPLIED,
            requested_by="김지원",
        )
        session.add(request)
        session.flush()
        reply = ExplanationReply(
            exp_id=request.exp_id, raw_text=REPLY_TEXT, provenance=Provenance.MOCK
        )
        session.add(reply)
        session.flush()
        return reply.reply_id


def g1_refs(engine) -> set[str]:
    with Session(engine) as session:
        return collect_refs(find_agencies_by_account(session, G1_ACCOUNT))


def tool_call(name: str, args: dict, call_id: str = "call_1") -> AIMessage:
    return AIMessage(
        content="", tool_calls=[{"name": name, "args": args, "id": call_id}]
    )


def assessment(**overrides) -> dict:
    values = {
        "judgement": "증빙 부족",
        "rationale": ["입금 계좌는 D-011 · D-037 등록계좌"],
        "missing_evidence": ["입금 대행 계약서", "세무대리인 계좌 명의"],
        "follow_up_request": "입금 대행 계약서와 세무대리인 계좌 명의를 보내 주세요",
        "confidence": 0.85,
    }
    return values | overrides


def scenario(engine, **structured_overrides) -> dict:
    """완료 기준 시나리오의 가짜 모델 답: 계좌 사용 대리점을 조회해 불일치를 찾는다."""
    ref = min(g1_refs(engine))
    structured = {
        "ExtractedClaims": [{"claims": [CLAIM_TEXT]}],
        "CheckResult": [
            {
                "verdict": "불일치",
                "finding": "그 계좌는 D-011 · D-037 의 등록 정산계좌입니다",
                "evidence_refs": [ref],
            }
        ],
        "ExplanationAssessment": [assessment()],
    }
    return structured | structured_overrides


def saved(engine, reply_id) -> tuple[dict, list[dict]]:
    with Session(engine) as session:
        reply = session.get(ExplanationReply, reply_id)
        checks = session.scalars(
            select(ExplanationCheck)
            .where(ExplanationCheck.reply_id == reply_id)
            .order_by(ExplanationCheck.seq)
        ).all()
        return (
            {c.name: getattr(reply, c.name) for c in ExplanationReply.__table__.c},
            [
                {c.name: getattr(x, c.name) for c in ExplanationCheck.__table__.c}
                for x in checks
            ],
        )


def run(engine, checkpointer, model, reply_id):
    with Session(engine) as session, session.begin():
        start_explanation_review(session, checkpointer, model, reply_id)


def test_completion_scenario_finds_account_mismatch(
    seeded_engine, checkpointer, reply_id, fake_explanation_model
):
    """세무대리인이 대신 입금 → DP-00013 계좌가 D-011 · D-037 등록계좌임을 찾아 불일치 + 증빙 부족."""
    model = fake_explanation_model(
        scenario(seeded_engine),
        tool_turns=[
            tool_call("list_deposits", {"agency_id": "D-024"}),
            tool_call("find_agencies_by_account", {"account": G1_ACCOUNT}, "call_2"),
        ],
    )
    run(seeded_engine, checkpointer, model, reply_id)

    reply, checks = saved(seeded_engine, reply_id)
    assert reply["ai_judgement"] == "증빙 부족"
    assert reply["verified"] is True and reply["fallback_used"] is False
    assert reply["model"] == "fake-explanation"
    assert reply["follow_up_request"].startswith("입금 대행 계약서")
    assert [c["verdict"] for c in checks] == ["불일치"]
    assert checks[0]["tool_used"] == ["list_deposits", "find_agencies_by_account"]
    assert checks[0]["evidence_ref"] and set(checks[0]["evidence_ref"]) <= g1_refs(
        seeded_engine
    )

    graph = build_explanation_review(checkpointer)
    assert pending_interrupts(graph, f"explanation_reply:{reply_id}") == [
        {"reply_id": reply_id}
    ]
    # 도구 결과가 모델에게 되돌려졌는지: 두 번째 도구 단계의 입력에 ToolMessage 가 있다.
    second_round = [m for name, m in model.calls if name == "tools"][1]
    assert any(isinstance(m, ToolMessage) for m in second_round)


def test_invented_evidence_is_dropped_and_verdict_downgraded(
    seeded_engine, checkpointer, reply_id, fake_explanation_model
):
    """도구가 돌려주지 않은 근거 행만 인용하면 불일치도 확인불가로 내려간다."""
    answers = scenario(seeded_engine)
    answers["CheckResult"] = [
        {
            "verdict": "불일치",
            "finding": "지어낸 근거",
            "evidence_refs": ["made_up.csv:99"],
        }
    ]
    model = fake_explanation_model(
        answers, tool_turns=[tool_call("list_deposits", {"agency_id": "D-024"})]
    )
    run(seeded_engine, checkpointer, model, reply_id)

    _, checks = saved(seeded_engine, reply_id)
    assert checks[0]["verdict"] == "확인불가"
    assert checks[0]["evidence_ref"] == []
    assert "확인불가로 내렸습니다" in checks[0]["finding"]


def test_multiple_claims_loop_back_into_check_claim(
    seeded_engine, checkpointer, reply_id, fake_explanation_model
):
    ref = min(g1_refs(seeded_engine))
    answers = scenario(seeded_engine)
    answers["ExtractedClaims"] = [{"claims": ["주장 하나", "주장 둘", "  "]}]
    answers["CheckResult"] = [
        {"verdict": "불일치", "finding": "첫째", "evidence_refs": [ref]},
        {"verdict": "확인불가", "finding": "둘째", "evidence_refs": []},
    ]
    model = fake_explanation_model(
        answers,
        tool_turns=[tool_call("find_agencies_by_account", {"account": G1_ACCOUNT})],
    )
    run(seeded_engine, checkpointer, model, reply_id)

    _, checks = saved(seeded_engine, reply_id)
    assert [(c["seq"], c["claim_text"], c["verdict"]) for c in checks] == [
        (1, "주장 하나", "불일치"),
        (2, "주장 둘", "확인불가"),
    ]


def test_assessment_that_ignores_mismatch_is_regenerated_once(
    seeded_engine, checkpointer, reply_id, fake_explanation_model
):
    """불일치가 있는데 증빙 충분이라 한 첫 답은 가드에 걸려, 문제를 알려 한 번 다시 받는다."""
    answers = scenario(seeded_engine)
    answers["ExplanationAssessment"] = [
        assessment(judgement="증빙 충분", follow_up_request=""),
        assessment(),
    ]
    model = fake_explanation_model(
        answers,
        tool_turns=[tool_call("find_agencies_by_account", {"account": G1_ACCOUNT})],
    )
    run(seeded_engine, checkpointer, model, reply_id)

    reply, _ = saved(seeded_engine, reply_id)
    assert reply["ai_judgement"] == "증빙 부족" and reply["fallback_used"] is False
    assert model.count("ExplanationAssessment") == 2
    retry_messages = [m for name, m in model.calls if name == "ExplanationAssessment"][
        1
    ]
    assert "이전 답에 문제가 있었습니다" in str(retry_messages[-1])


def test_two_bad_assessments_fall_back_but_keep_claim_checks(
    seeded_engine, checkpointer, reply_id, fake_explanation_model
):
    bad = assessment(judgement="증빙 충분", follow_up_request="")
    answers = scenario(seeded_engine)
    answers["ExplanationAssessment"] = [bad, bad]
    model = fake_explanation_model(
        answers,
        tool_turns=[tool_call("find_agencies_by_account", {"account": G1_ACCOUNT})],
    )
    run(seeded_engine, checkpointer, model, reply_id)

    reply, checks = saved(seeded_engine, reply_id)
    assert reply["fallback_used"] is True and reply["ai_judgement"] is None
    assert reply["verified"] is False and reply["model"] is None
    assert len(checks) == 1  # 종합 판단이 대체 모드여도 주장별 대조 결과는 남는다.


def test_assessment_call_failure_twice_falls_back(
    seeded_engine, checkpointer, reply_id, fake_explanation_model
):
    answers = scenario(seeded_engine)
    answers["ExplanationAssessment"] = [
        TimeoutError("시간 초과"),
        TimeoutError("시간 초과"),
    ]
    model = fake_explanation_model(answers)
    run(seeded_engine, checkpointer, model, reply_id)
    reply, _ = saved(seeded_engine, reply_id)
    assert reply["fallback_used"] is True


def test_no_model_is_fallback_with_pending_decision(
    seeded_engine, checkpointer, reply_id
):
    run(seeded_engine, checkpointer, None, reply_id)
    reply, checks = saved(seeded_engine, reply_id)
    assert reply["fallback_used"] is True and reply["ai_judgement"] is None
    assert checks == []
    graph = build_explanation_review(checkpointer)
    assert pending_interrupts(graph, f"explanation_reply:{reply_id}")


def test_extraction_failure_falls_back(
    seeded_engine, checkpointer, reply_id, fake_explanation_model
):
    model = fake_explanation_model({"ExtractedClaims": [TimeoutError("시간 초과")]})
    run(seeded_engine, checkpointer, model, reply_id)
    reply, checks = saved(seeded_engine, reply_id)
    assert reply["fallback_used"] is True and checks == []


def test_no_claims_goes_straight_to_assessment(
    seeded_engine, checkpointer, reply_id, fake_explanation_model
):
    """뽑을 주장이 없는 회신: 대조 없이 종합 판단으로 가고, 확인한 주장이 없으니 증빙 부족이어야 한다."""
    model = fake_explanation_model(
        {
            "ExtractedClaims": [{"claims": []}],
            "ExplanationAssessment": [
                assessment(judgement="증빙 충분", follow_up_request=""),
                assessment(),
            ],
        }
    )
    run(seeded_engine, checkpointer, model, reply_id)
    reply, checks = saved(seeded_engine, reply_id)
    assert checks == [] and reply["ai_judgement"] == "증빙 부족"
    assert model.count("tools") == 0


def test_unknown_tool_and_bad_arguments_do_not_break_the_graph(
    seeded_engine, checkpointer, reply_id, fake_explanation_model
):
    """모델이 없는 도구나 틀린 인자를 부르면 오류 문장을 되돌려주고 그래프는 계속 돈다."""
    model = fake_explanation_model(
        scenario(seeded_engine)
        | {
            "CheckResult": [
                {"verdict": "확인불가", "finding": "조회 실패", "evidence_refs": []}
            ]
        },
        tool_turns=[
            tool_call("no_such_tool", {}),
            tool_call("list_deposits", {"wrong_arg": 1}, "call_2"),
            tool_call("list_deposits", {"agency_id": "D-999"}, "call_3"),
        ],
    )
    run(seeded_engine, checkpointer, model, reply_id)

    _, checks = saved(seeded_engine, reply_id)
    assert checks[0]["verdict"] == "확인불가"
    assert checks[0]["tool_used"] == ["no_such_tool", "list_deposits"]
    tool_texts = [
        m.content
        for name, msgs in model.calls
        if name == "CheckResult"
        for m in msgs
        if isinstance(m, ToolMessage)
    ]
    assert "없는 도구입니다" in tool_texts[0]
    assert "도구 실행 실패" in tool_texts[1]
    assert "D-999" in tool_texts[2]


def test_tool_rounds_are_capped(
    seeded_engine, checkpointer, reply_id, fake_explanation_model
):
    """모델이 계속 도구만 부르면 MAX_TOOL_STEPS 라운드에서 멈추고 판정을 받는다."""
    turns = [
        tool_call("list_deposits", {"agency_id": "D-024"}, f"call_{i}")
        for i in range(MAX_TOOL_STEPS + 3)
    ]
    answers = scenario(seeded_engine)
    answers["CheckResult"] = [
        {"verdict": "확인불가", "finding": "상한", "evidence_refs": []}
    ]
    model = fake_explanation_model(answers, tool_turns=turns)
    run(seeded_engine, checkpointer, model, reply_id)
    assert model.count("tools") == MAX_TOOL_STEPS
    assert model.count("CheckResult") == 1


def test_check_call_failure_marks_only_that_claim_unverifiable(
    seeded_engine, checkpointer, reply_id, fake_explanation_model
):
    answers = scenario(seeded_engine)
    answers["CheckResult"] = [TimeoutError("시간 초과")]
    model = fake_explanation_model(answers)
    run(seeded_engine, checkpointer, model, reply_id)
    reply, checks = saved(seeded_engine, reply_id)
    assert checks[0]["verdict"] == "확인불가"
    assert "대조하지 못했습니다" in checks[0]["finding"]
    assert reply["ai_judgement"] == "증빙 부족"


def test_start_conflicts(seeded_engine, checkpointer, reply_id, fake_explanation_model):
    with (
        Session(seeded_engine) as session,
        session.begin(),
        pytest.raises(LookupError),
    ):
        start_explanation_review(session, checkpointer, None, 9999)
    run(seeded_engine, checkpointer, None, reply_id)
    # 이미 확인을 기다리는 검토는 다시 시작할 수 없다.
    with pytest.raises(InvalidRunStateError, match="이미 사람 결정을 기다리고"):
        run(seeded_engine, checkpointer, None, reply_id)
    # 확인이 끝난 회신은 검토 대상이 아니다.
    with Session(seeded_engine) as session, session.begin():
        reply = session.get(ExplanationReply, reply_id)
        session.get(
            ExplanationRequest, reply.exp_id
        ).status = ExplanationStatus.CONFIRMED
    with pytest.raises(InvalidRunStateError, match="확인 전 회신만"):
        run(seeded_engine, checkpointer, None, reply_id)


def test_record_human_confirmation_ends_the_thread(
    seeded_engine, checkpointer, reply_id
):
    run(seeded_engine, checkpointer, None, reply_id)
    with Session(seeded_engine) as session, session.begin():
        assert record_human_confirmation(
            session,
            checkpointer,
            reply_id,
            judgement=ExplanationJudgement.INSUFFICIENT,
            reason="증빙 부족",
            actor="김지원",
        )
    graph = build_explanation_review(checkpointer)
    assert pending_interrupts(graph, f"explanation_reply:{reply_id}") == []
    # 기다리는 검토가 없으면 아무것도 안 하고 False.
    with Session(seeded_engine) as session, session.begin():
        assert not record_human_confirmation(
            session,
            checkpointer,
            reply_id,
            judgement=ExplanationJudgement.INSUFFICIENT,
            reason="증빙 부족",
            actor="김지원",
        )
