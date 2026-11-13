"""부서 영향 · 영업 의견(23) 테스트.

상계 제안이 생기면 영업지원팀에 의견 작업이 열리고, 영업 의견(대안)이 AI 추천의 사실과 재무 결정에 들어가며,
지급 후 회수 약정이면 재무에 회수 약정 관리 작업이 열린다. 원본 6월분 G1 승인 뒤로 본다.
RB-00054 상계 한도 = 장려금 1,373,515원.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_review_model
from app.core.database import make_engine
from app.main import create_app
from app.models import EventLog, OffsetProposal, Task
from app.models.enums import Decision, SalesAlternative
from app.services.approval import InsufficientAuthorityError, decide_approval
from app.services.claim_state import InvalidTransitionError
from app.services.intake import intake_period
from app.services.offset import (
    COLLECTION_TASK,
    SALES_TASK,
    InvalidOffsetError,
    decide_offset,
    open_offset_reviews,
    recommend_offset,
    submit_sales_opinion,
)
from app.services.payment import order_payment

G1_CLAIMS = ["RB-00054", "RB-00120", "RB-00180"]
MAX_054 = 1_373_515
EXECUTIVE = {"actor": "박임원", "role": "영업임원"}
SUPPORT = {"actor": "김지원", "role": "영업지원팀"}
FINANCE = {"actor": "이재무", "role": "재무"}
OPINION = "D-011 은 하반기 신규 판촉 대상이라 전액 상계는 관계 부담이 크다"


@pytest.fixture
def g1_engine(seeded_engine):
    with Session(seeded_engine) as session, session.begin():
        intake_period(session, "2026-06")
        _, claims = decide_approval(
            session, 1, decision=Decision.APPROVE, reason="", **EXECUTIVE
        )
        assert open_offset_reviews(session, claims) == [1, 2, 3]
    return seeded_engine


def opinion(session, alternative, amount=None, **who):
    return submit_sales_opinion(
        session,
        1,
        alternative=alternative,
        amount_krw=amount,
        opinion=OPINION,
        **(who or SUPPORT),
    )


def tasks(session, task_type) -> list[tuple[str, str, str]]:
    rows = session.scalars(
        select(Task).where(Task.task_type == task_type).order_by(Task.task_id)
    )
    return [(t.ref_id, t.dept, t.status) for t in rows]


def test_offset_review_opens_sales_task_per_claim(g1_engine):
    """상계 제안마다 영업지원팀 의견 작업이 열린다. 상태 전이 작업이 아니라 손으로도 닫을 수 있다."""
    with Session(g1_engine) as session:
        assert tasks(session, SALES_TASK) == [
            (r, "영업지원팀", "열림") for r in G1_CLAIMS
        ]
        task = session.scalars(select(Task).where(Task.task_type == SALES_TASK)).first()
        assert task.trigger_status is None
        assert "상계 한도 1,373,515원" in task.detail


def test_partial_opinion_reaches_ai_and_closes_task(g1_engine, fake_model):
    """부분 상계 의견은 저장 · 이력에 남고, 영업 작업이 닫히며, AI 추천의 사실에 들어간다."""
    model = fake_model(
        {
            "offset_amount_krw": 700_000,
            "rationale": ["영업 의견의 관계 부담을 반영해 절반 상계"],
            "counter_evidence": [],
            "confidence": 0.7,
        }
    )
    with Session(g1_engine) as session, session.begin():
        proposal = opinion(session, SalesAlternative.PARTIAL_OFFSET, 700_000)
        assert (proposal.sales_alternative, proposal.sales_amount_krw) == (
            "부분 상계",
            700_000,
        )
        assert tasks(session, SALES_TASK)[0] == ("RB-00054", "영업지원팀", "완료")
        event = session.scalars(
            select(EventLog).where(EventLog.entity_type == "offset_proposal")
        ).one()
        assert (event.actor, event.from_status, event.to_status) == (
            "김지원",
            "재무검토",
            "재무검토",
        )
        assert event.reason.startswith("영업 의견 [주장]: 부분 상계")
        recommend_offset(session, 1, model)
    facts = model.calls[0][1][1]
    assert '"대안": "부분 상계"' in facts and OPINION in facts


@pytest.mark.parametrize(
    ("alternative", "sales_amount", "finance_amount", "followed"),
    [
        (SalesAlternative.PARTIAL_OFFSET, 700_000, 700_000, True),
        (SalesAlternative.PARTIAL_OFFSET, 700_000, MAX_054, False),
        (SalesAlternative.FULL_OFFSET, None, MAX_054, True),
        (SalesAlternative.PAY_WITH_PLAN, None, MAX_054, False),
    ],
)
def test_finance_decision_records_whether_sales_was_followed(
    g1_engine, alternative, sales_amount, finance_amount, followed
):
    """재무가 상계를 승인하면, 그 금액이 영업 대안과 같은지 sales_followed 로 남는다."""
    with Session(g1_engine) as session, session.begin():
        opinion(session, alternative, sales_amount)
        proposal, _ = decide_offset(
            session,
            1,
            decision=Decision.APPROVE,
            amount_krw=finance_amount,
            reason="",
            **FINANCE,
        )
        assert proposal.sales_followed is followed


def test_pay_with_collection_plan_changes_next_work(g1_engine):
    """지급 후 회수 약정: 상계 없이 전액 지급하되 기한이 남고, 재무에 회수 약정 관리 작업이 열린다."""
    with Session(g1_engine) as session, session.begin():
        opinion(session, SalesAlternative.PAY_WITH_PLAN)
        proposal, _ = decide_offset(
            session,
            1,
            decision=Decision.REJECT,
            amount_krw=None,
            reason="영업 의견대로 관계 유지, 9월 말까지 회수 약정",
            collection_due_date=date(2026, 9, 30),
            **FINANCE,
        )
        assert (proposal.status, proposal.collection_due_date) == (
            "재무반려",
            date(2026, 9, 30),
        )
        assert proposal.sales_followed is True
        assert tasks(session, COLLECTION_TASK) == [("RB-00054", "재무", "열림")]
        assert order_payment(session, "RB-00054", **FINANCE).amount_krw == MAX_054


def test_decision_without_opinion_closes_sales_task(g1_engine):
    """영업 의견 없이 재무가 결정해도 된다. 비교 대상이 없어 sales_followed 는 비고, 영업 작업은 닫힌다."""
    with Session(g1_engine) as session, session.begin():
        proposal, _ = decide_offset(
            session,
            1,
            decision=Decision.REJECT,
            amount_krw=None,
            reason="관계 고려",
            **FINANCE,
        )
        assert (proposal.sales_followed, proposal.collection_due_date) == (None, None)
        assert tasks(session, SALES_TASK)[0][2] == "완료"
        assert tasks(session, COLLECTION_TASK) == []


def test_sales_opinion_rules(g1_engine):
    """영업 역할만, 부분 상계는 1원 ~ 한도 미만, 재무 결정 뒤에는 낼 수 없다. 다시 내면 덮어쓴다."""
    with Session(g1_engine) as session, session.begin():
        with pytest.raises(InsufficientAuthorityError):
            opinion(session, SalesAlternative.FULL_OFFSET, **FINANCE)
        with pytest.raises(InvalidOffsetError, match="미만"):
            opinion(session, SalesAlternative.PARTIAL_OFFSET, MAX_054)
        opinion(session, SalesAlternative.FULL_OFFSET, **EXECUTIVE)
        proposal = opinion(session, SalesAlternative.PAY_WITH_PLAN)
        assert (proposal.sales_alternative, proposal.sales_by) == (
            "지급 후 회수 약정",
            "김지원",
        )
        decide_offset(
            session,
            1,
            decision=Decision.APPROVE,
            amount_krw=MAX_054,
            reason="",
            **FINANCE,
        )
        with pytest.raises(InvalidTransitionError, match="재무 결정 전"):
            opinion(session, SalesAlternative.FULL_OFFSET)
        assert session.get(OffsetProposal, 1).sales_followed is False


# ---------------------------------------------------------------- API


@pytest.fixture
def client(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    app = create_app(tmp_path / "missing", engine=engine)
    app.dependency_overrides[get_review_model] = lambda: None
    with TestClient(app) as c:
        assert c.post("/api/claims/intake", params={"period": "2026-06"}).is_success
        body = {"decision": "승인", "reason": "", **EXECUTIVE}
        assert c.post("/api/approvals/1/decision", json=body).is_success
        yield c
    engine.dispose()


def test_api_sales_opinion_then_plan_shows_in_detail(client):
    body = {"alternative": "지급 후 회수 약정", "opinion": OPINION, **SUPPORT}
    res = client.post("/api/offsets/1/sales-opinion", json=body)
    assert res.status_code == 200
    assert res.json()["sales_at"].endswith("Z")

    decision = {
        "decision": "반려",
        "reason": "회수 약정",
        "collection_due_date": "2026-09-30",
        **FINANCE,
    }
    res = client.post("/api/offsets/1/decision", json=decision)
    assert res.status_code == 200
    offset = client.get("/api/claims/RB-00054").json()["offsets"][0]
    assert (
        offset["sales_alternative"],
        offset["collection_due_date"],
        offset["sales_followed"],
    ) == ("지급 후 회수 약정", "2026-09-30", True)
    finance = client.get("/api/tasks", params={"dept": "재무"}).json()
    assert finance[-1]["task_type"] == "회수 약정 관리"


@pytest.mark.parametrize(
    ("url", "body", "status_code"),
    [
        (
            "/api/offsets/1/sales-opinion",
            {"alternative": "전액 상계", "opinion": OPINION, **FINANCE},
            403,
        ),
        (
            "/api/offsets/9/sales-opinion",
            {"alternative": "전액 상계", "opinion": OPINION, **SUPPORT},
            404,
        ),
        (
            "/api/offsets/1/sales-opinion",
            {"alternative": "부분 상계", "opinion": OPINION, **SUPPORT},
            422,
        ),
        (
            "/api/offsets/1/sales-opinion",
            {
                "alternative": "전액 상계",
                "amount_krw": 1,
                "opinion": OPINION,
                **SUPPORT,
            },
            422,
        ),
        (
            "/api/offsets/1/sales-opinion",
            {"alternative": "전액 상계", "opinion": "  ", **SUPPORT},
            422,
        ),
        (
            "/api/offsets/1/sales-opinion",
            {
                "alternative": "부분 상계",
                "amount_krw": MAX_054,
                "opinion": OPINION,
                **SUPPORT,
            },
            422,
        ),
        (
            "/api/offsets/1/decision",
            {
                "decision": "승인",
                "offset_amount_krw": 1,
                "reason": "",
                "collection_due_date": "2026-09-30",
                **FINANCE,
            },
            422,
        ),
    ],
)
def test_api_sales_opinion_errors(client, url, body, status_code):
    """영업 아님 403, 없는 제안 404, 부분 상계액 빠짐 · 다른 대안에 금액 · 빈 의견 · 한도 이상 ·
    승인에 회수 약정 기한은 422."""
    res = client.post(url, json=body)
    assert res.status_code == status_code, res.text


def test_api_sales_opinion_after_decision_is_409(client):
    body = {"decision": "반려", "reason": "관계 고려", **FINANCE}
    assert client.post("/api/offsets/1/decision", json=body).is_success
    res = client.post(
        "/api/offsets/1/sales-opinion",
        json={"alternative": "전액 상계", "opinion": OPINION, **SUPPORT},
    )
    assert res.status_code == 409
