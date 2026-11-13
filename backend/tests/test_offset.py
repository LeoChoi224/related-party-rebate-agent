"""상계 검토(필수 확장) [가정] 테스트.

앞부분은 서비스로 원본 6월분 G1 승인 뒤의 상계 흐름(제안 → 재무 결정 → 대리점 동의 [모의] → 지급)을 보고,
가운데는 AI 상계액 추천(가짜 모델 · 대체 모드 · 가드)을, 뒷부분은 API 의 403 · 404 · 409 · 422 를 본다.
원본 숫자: G1 90일 초과 연체 5건 29,202,840원, G1 6월 장려금 RB-00054 1,373,515 · RB-00120 1,189,046 ·
RB-00180 1,325,536(합 3,888,097원).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.agents.guards import check_offset_advice
from app.api.deps import get_review_model
from app.core.database import make_engine
from app.main import create_app
from app.models import (
    ARAdjustment,
    ARItem,
    OffsetProposal,
    PaymentOrder,
    RebateClaim,
    Task,
)
from app.models.enums import AgencyConsent, BankResult, ClaimStatus, Decision
from app.schemas.offset import OffsetAdvice
from app.services.approval import (
    InsufficientAuthorityError,
    decide_approval,
    decide_claim,
)
from app.services.claim_state import InvalidTransitionError
from app.services.intake import intake_period
from app.services.master_change import apply_master_change
from app.services.offset import (
    InvalidOffsetError,
    apply_agency_consent,
    decide_offset,
    open_offset_reviews,
    overdue_items,
    payable_krw,
    recommend_offset,
)
from app.services.payment import apply_bank_reply, order_payment

G1_CLAIMS = ["RB-00054", "RB-00120", "RB-00180"]
G1_AMOUNTS = [1_373_515, 1_189_046, 1_325_536]
G1_OVERDUE = 29_202_840
D001_JUNE = "RB-00006"
EXECUTIVE = {"actor": "박임원", "role": "영업임원"}
SUPPORT = {"actor": "김지원", "role": "영업지원팀"}
FINANCE = {"actor": "이재무", "role": "재무"}


def approve_g1(session: Session) -> list[int]:
    """6월분 접수 뒤 영업임원이 G1 승인 요청을 승인하고, API 처럼 상계 검토를 연다."""
    intake_period(session, "2026-06")
    _, claims = decide_approval(
        session, 1, decision=Decision.APPROVE, reason="", **EXECUTIVE
    )
    return open_offset_reviews(session, claims)


@pytest.fixture
def g1_engine(seeded_engine):
    with Session(seeded_engine) as session, session.begin():
        assert approve_g1(session) == [1, 2, 3]
    return seeded_engine


def finance_approves(session: Session, offset_id: int, amount: int) -> None:
    decide_offset(
        session,
        offset_id,
        decision=Decision.APPROVE,
        amount_krw=amount,
        reason="",
        **FINANCE,
    )


def status_of(session: Session, rebate_id: str) -> str:
    return session.get(RebateClaim, rebate_id).status


def g1_overdue_left(session: Session) -> int:
    return sum(i.remaining_krw for i in overdue_items(session, 1, "D-011"))


def test_g1_approval_opens_offset_review_per_claim(g1_engine):
    """G1 3건은 승인 직후 상계검토가 되고, 건마다 장려금액만큼의 상계 한도와 재무 작업이 생긴다."""
    with Session(g1_engine) as session:
        proposals = session.scalars(
            select(OffsetProposal).order_by(OffsetProposal.offset_id)
        ).all()
        assert [(p.rebate_id, p.max_offset_krw, p.status) for p in proposals] == [
            (r, a, "재무검토") for r, a in zip(G1_CLAIMS, G1_AMOUNTS, strict=True)
        ]
        assert {p.overdue_total_krw for p in proposals} == {G1_OVERDUE}
        assert [status_of(session, r) for r in G1_CLAIMS] == ["상계검토"] * 3
        tasks = session.scalars(
            select(Task.ref_id).where(
                Task.task_type == "상계 검토", Task.status == "열림"
            )
        ).all()
        assert tasks == G1_CLAIMS


def test_overdue_items_are_own_agency_first_then_oldest(g1_engine):
    """상계 순서: 이 건의 대리점(D-024) 채권 먼저, 같은 대리점 안에서는 오래된 것 먼저."""
    with Session(g1_engine) as session:
        items = overdue_items(session, 1, "D-024")
    assert [(i.ar_id, i.aging_days) for i in items] == [
        ("AR-D00109", 162),
        ("AR-D00108", 133),
        ("AR-D00125", 176),
        ("AR-D00092", 164),
        ("AR-D00090", 137),
    ]
    assert items[0].source_file.endswith("fin_ar_aging_cv.csv")


def test_standalone_agency_is_not_offset(seeded_engine):
    """단독 대리점(D-001)은 90일 초과 연체가 있어도 상계 대상이 아니다 [가정]. 승인 그대로 지급한다."""
    with Session(seeded_engine) as session, session.begin():
        intake_period(session, "2026-06")
        claim = decide_claim(
            session, D001_JUNE, decision=Decision.APPROVE, reason="", **SUPPORT
        )
        assert open_offset_reviews(session, [claim]) == []
        assert claim.status == ClaimStatus.APPROVED
        assert order_payment(session, D001_JUNE, **FINANCE).amount_krw == 988_932


def test_full_offset_changes_payment_and_receivable(g1_engine):
    """완료 기준: 확장이 없으면 G1 에 현금 3,888,097원이 나가지만, 전액 상계하면 지급 0원 · 연체 잔액이 줄어든다."""
    with Session(g1_engine) as session, session.begin():
        for offset_id, amount in enumerate(G1_AMOUNTS, start=1):
            finance_approves(session, offset_id, amount)
            apply_agency_consent(session, offset_id, AgencyConsent.CONSENT)

        assert [status_of(session, r) for r in G1_CLAIMS] == ["상계완료"] * 3
        assert session.scalar(select(func.count()).select_from(PaymentOrder)) == 0
        adjustments = session.execute(
            select(
                ARAdjustment.ar_id, ARAdjustment.amount_krw, ARAdjustment.provenance
            ).order_by(ARAdjustment.id)
        ).all()
        # 각 건은 자기 대리점의 가장 오래된 연체 채권부터 줄인다. 원본 잔액은 그대로다.
        assert adjustments == [
            ("AR-D00092", 1_373_515, "가정"),
            ("AR-D00109", 1_189_046, "가정"),
            ("AR-D00125", 1_325_536, "가정"),
        ]
        assert session.get(ARItem, "AR-D00092").outstanding_krw == 4_337_720
        assert g1_overdue_left(session) == G1_OVERDUE - 3_888_097 == 25_314_743
        # 상계완료로 넘어가며 상계 검토 작업이 닫힌다.
        assert (
            session.scalar(
                select(func.count())
                .select_from(Task)
                .where(Task.task_type == "상계 검토", Task.status != "완료")
            )
            == 0
        )


def test_partial_offset_pays_the_difference(g1_engine):
    """일부만 상계하면 건은 상계검토에 남고, 재무가 차액을 지급 지시해 지급완료까지 간다."""
    with Session(g1_engine) as session, session.begin():
        finance_approves(session, 1, 373_515)
        _, claim = apply_agency_consent(session, 1, AgencyConsent.CONSENT)
        assert (claim.status, payable_krw(session, claim)) == ("상계검토", 1_000_000)

        order = order_payment(session, "RB-00054", **FINANCE)
        assert (order.amount_krw, claim.status) == (1_000_000, "지급지시")
        apply_bank_reply(session, order.payment_id, BankResult.SUCCESS)
        assert claim.status == "지급완료"
        assert g1_overdue_left(session) == G1_OVERDUE - 373_515


@pytest.mark.parametrize("path", ["재무반려", "동의거절"])
def test_no_offset_pays_in_full(g1_engine, path):
    """재무가 상계하지 않기로 하거나 대리점이 거절하면 채권은 그대로이고 장려금 전액을 지급한다."""
    with Session(g1_engine) as session, session.begin():
        if path == "재무반려":
            decide_offset(
                session,
                1,
                decision=Decision.REJECT,
                amount_krw=None,
                reason="대리점 관계 고려",
                **FINANCE,
            )
        else:
            finance_approves(session, 1, 1_373_515)
            apply_agency_consent(session, 1, AgencyConsent.REFUSE)
        assert session.get(OffsetProposal, 1).status == path

        assert order_payment(session, "RB-00054", **FINANCE).amount_krw == 1_373_515
        assert g1_overdue_left(session) == G1_OVERDUE


def test_payment_is_blocked_until_offset_is_done(g1_engine):
    """재무 결정 전 · 대리점 동의 전에는 지급 지시가 409 다(상계 검토를 건너뛰는 지급 차단)."""
    with Session(g1_engine) as session, session.begin():
        with pytest.raises(InvalidTransitionError, match="재무검토"):
            order_payment(session, "RB-00054", **FINANCE)
        finance_approves(session, 1, 1_373_515)
        with pytest.raises(InvalidTransitionError, match="동의대기"):
            order_payment(session, "RB-00054", **FINANCE)


def test_decision_rules(g1_engine):
    """재무만 결정하고, 상계액은 1~한도 안이어야 하며, 결정 · 동의는 한 번씩만 된다."""
    with Session(g1_engine) as session, session.begin():
        with pytest.raises(InsufficientAuthorityError):
            decide_offset(
                session,
                1,
                decision=Decision.APPROVE,
                amount_krw=1,
                reason="",
                **EXECUTIVE,
            )
        with pytest.raises(InvalidOffsetError, match="1,373,515"):
            finance_approves(session, 1, 1_373_516)
        with pytest.raises(InvalidTransitionError, match="동의를 기다리는"):
            apply_agency_consent(session, 1, AgencyConsent.CONSENT)
        finance_approves(session, 1, 1_373_515)
        with pytest.raises(InvalidTransitionError, match="이미 재무가 결정"):
            finance_approves(session, 1, 1)
        apply_agency_consent(session, 1, AgencyConsent.CONSENT)
        with pytest.raises(InvalidTransitionError):
            apply_agency_consent(session, 1, AgencyConsent.CONSENT)


def test_open_proposals_share_the_group_balance(seeded_engine):
    """그룹 연체 잔액이 모자라면 앞 건이 잡은 몫을 빼고 한도를 정하고, 남은 것이 없으면 제안 없이 승인 그대로다."""
    with Session(seeded_engine) as session, session.begin():
        # 테스트 DB 에서만 잔액을 줄인다: G1 연체 중 AR-D00125 만 2,000,000원이 남았다고 둔다.
        session.execute(
            update(ARItem)
            .where(ARItem.agency_id.in_(["D-011", "D-024", "D-037"]))
            .values(outstanding_krw=0)
        )
        session.execute(
            update(ARItem)
            .where(ARItem.ar_id == "AR-D00125")
            .values(outstanding_krw=2_000_000)
        )
        assert approve_g1(session) == [1, 2]
        maxima = session.scalars(
            select(OffsetProposal.max_offset_krw).order_by(OffsetProposal.offset_id)
        ).all()
        assert maxima == [1_373_515, 2_000_000 - 1_373_515]
        assert status_of(session, "RB-00180") == "승인"


def test_master_change_cancels_open_offsets(g1_engine):
    """정정 신고로 그룹이 바뀌면 상계검토 건은 재검토필요가 되고 열린 제안은 취소된다."""
    with Session(g1_engine) as session, session.begin():
        apply_master_change(
            session,
            "D-037",
            attr_type="대표자",
            new_value="김새대표",
            effective_date=None,
            reported_text="",
            **SUPPORT,
        )
        assert [status_of(session, r) for r in G1_CLAIMS] == ["재검토필요"] * 3
        assert set(session.scalars(select(OffsetProposal.status))) == {"취소"}


# ---------------------------------------------------------------- AI 상계액 추천


def advice(amount: int, confidence: float = 0.8, rationale=None) -> dict:
    return {
        "offset_amount_krw": amount,
        "rationale": ["AR-D00092 164일 연체 (fin_ar_aging_cv.csv:93)"]
        if rationale is None
        else rationale,
        "counter_evidence": ["대리점 관계 부담"],
        "confidence": confidence,
    }


def test_ai_recommendation_is_saved_and_compared(g1_engine, fake_model):
    """추천이 가드를 통과하면 [주장] 으로 저장되고, 재무가 같은 금액을 고르면 일치로 남는다."""
    model = fake_model(advice(1_373_515))
    with Session(g1_engine) as session, session.begin():
        proposal = recommend_offset(session, 1, model)
        assert (proposal.ai_amount_krw, proposal.verified, proposal.model) == (
            1_373_515,
            True,
            "fake-review",
        )
        finance_approves(session, 1, 1_373_515)
        assert session.get(OffsetProposal, 1).agreed is True
    facts = model.calls[0][1][1]
    assert '"max_offset_krw": 1373515' in facts and "AR-D00092" in facts


def test_ai_over_limit_is_retried_with_the_problem(g1_engine, fake_model):
    """한도를 넘는 추천은 깎지 않고 문제를 알려 한 번 더 묻는다."""
    model = fake_model(advice(5_000_000), advice(1_000_000))
    with Session(g1_engine) as session, session.begin():
        assert recommend_offset(session, 1, model).ai_amount_krw == 1_000_000
        decide_offset(
            session,
            1,
            decision=Decision.REJECT,
            amount_krw=None,
            reason="관계 고려",
            **FINANCE,
        )
        # 상계하지 않은 결정은 AI 가 0원을 권했을 때만 일치다.
        assert session.get(OffsetProposal, 1).agreed is False
    assert len(model.calls) == 2
    assert "상계 한도" in model.calls[1][-1][1]


@pytest.mark.parametrize(
    "answers",
    [
        (),
        (RuntimeError("timeout"), advice(-1)),
        (advice(1, confidence=1.5), advice(1, rationale=[])),
    ],
    ids=["no-model", "error-then-negative", "bad-confidence-then-empty"],
)
def test_ai_falls_back_without_model_or_after_two_failures(
    g1_engine, fake_model, answers
):
    """모델이 없거나 2회 실패하면 대체 모드: 추천 없이 기록하고, 재무 결정은 그대로 된다(일치 비교 없음)."""
    model = fake_model(*answers) if answers else None
    with Session(g1_engine) as session, session.begin():
        proposal = recommend_offset(session, 1, model)
        assert (proposal.ai_amount_krw, proposal.fallback_used, proposal.model) == (
            None,
            True,
            None,
        )
        finance_approves(session, 1, 1_373_515)
        assert session.get(OffsetProposal, 1).agreed is None


def test_ai_recommendation_only_before_finance_decision(g1_engine, fake_model):
    with Session(g1_engine) as session, session.begin():
        finance_approves(session, 1, 1_373_515)
        with pytest.raises(InvalidTransitionError, match="재무 결정 전"):
            recommend_offset(session, 1, fake_model(advice(1)))


@pytest.mark.parametrize(
    ("amount", "confidence", "ok"),
    [
        (0, 0.5, True),
        (100, 1.0, True),
        (101, 0.5, False),
        (-1, 0.5, False),
        (50, -0.1, False),
    ],
)
def test_offset_guard_bounds(amount, confidence, ok):
    """0 원(상계 안 함) ~ 한도는 통과, 한도 초과 · 음수 · 확신도 범위 밖은 실패."""
    result = check_offset_advice(
        OffsetAdvice(**advice(amount, confidence)), max_offset_krw=100
    )
    assert result.ok is ok


# ---------------------------------------------------------------- API


@pytest.fixture
def api_engine(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    yield eng
    eng.dispose()


@pytest.fixture
def client(tmp_path, api_engine):
    """6월분 접수와 G1 승인까지 마친 클라이언트. 모델은 없음(대체 모드)."""
    app = create_app(tmp_path / "missing", engine=api_engine)
    app.dependency_overrides[get_review_model] = lambda: None
    with TestClient(app) as c:
        assert c.post("/api/claims/intake", params={"period": "2026-06"}).is_success
        body = {"decision": "승인", "reason": "", **EXECUTIVE}
        res = c.post("/api/approvals/1/decision", json=body)
        assert res.json()["offset_ids"] == [1, 2, 3]
        yield c


def test_api_offset_flow_in_claim_detail(client):
    """AI 추천(대체 모드) → 재무 승인 → 대리점 동의 [모의] 가 건 상세의 상계 칸 · 지급할 금액에 그대로 보인다."""
    rec = client.post("/api/offsets/1/recommend")
    assert rec.status_code == 200 and rec.json()["fallback_used"] is True

    body = {"decision": "승인", "offset_amount_krw": 373_515, "reason": "", **FINANCE}
    res = client.post("/api/offsets/1/decision", json=body)
    assert res.status_code == 200
    assert (res.json()["offset"]["status"], res.json()["payable_krw"]) == (
        "동의대기",
        1_373_515,
    )

    res = client.post("/api/offsets/1/agency-consent", json={"consent": "동의"})
    assert res.status_code == 200
    assert (res.json()["claim_status"], res.json()["payable_krw"]) == (
        "상계검토",
        1_000_000,
    )
    detail = client.get("/api/claims/RB-00054").json()
    offset = detail["offsets"][0]
    assert (offset["agency_consent"], offset["consent_provenance"]) == ("동의", "모의")
    assert offset["adjustments"][0]["ar_id"] == "AR-D00092"
    assert offset["adjustments"][0]["applied_at"].endswith("Z")
    assert offset["overdue_items"][0]["remaining_krw"] == 4_337_720 - 373_515
    assert detail["payable_krw"] == 1_000_000

    order = client.post("/api/claims/RB-00054/payment-order", json=FINANCE)
    assert (order.status_code, order.json()["amount_krw"]) == (200, 1_000_000)


def test_api_full_offset_ends_in_offset_done(client):
    body = {"decision": "승인", "offset_amount_krw": 1_189_046, "reason": "", **FINANCE}
    assert client.post("/api/offsets/2/decision", json=body).is_success
    res = client.post("/api/offsets/2/agency-consent", json={"consent": "동의"})
    assert (res.json()["claim_status"], res.json()["payable_krw"]) == ("상계완료", 0)
    events = client.get("/api/events", params={"rebate_id": "RB-00120"}).json()
    assert (events[0]["actor"], events[0]["to_status"]) == ("대리점", "상계완료")


@pytest.mark.parametrize(
    ("url", "body", "status_code"),
    [
        (
            "/api/offsets/1/decision",
            {"decision": "승인", "offset_amount_krw": 1, "reason": "", **SUPPORT},
            403,
        ),
        (
            "/api/offsets/9/decision",
            {"decision": "승인", "offset_amount_krw": 1, "reason": "", **FINANCE},
            404,
        ),
        ("/api/offsets/9/recommend", None, 404),
        ("/api/offsets/9/agency-consent", {"consent": "동의"}, 404),
        ("/api/offsets/1/agency-consent", {"consent": "동의"}, 409),
        (
            "/api/offsets/1/decision",
            {
                "decision": "승인",
                "offset_amount_krw": 9_999_999,
                "reason": "",
                **FINANCE,
            },
            422,
        ),
        ("/api/offsets/1/decision", {"decision": "승인", "reason": "", **FINANCE}, 422),
        (
            "/api/offsets/1/decision",
            {"decision": "반려", "reason": " ", **FINANCE},
            422,
        ),
        ("/api/offsets/1/agency-consent", {"consent": "보류"}, 422),
        ("/api/claims/RB-00054/payment-order", FINANCE, 409),
    ],
)
def test_api_offset_errors(client, url, body, status_code):
    """재무 아님 403, 없는 제안 404, 순서 어긋남 · 상계 전 지급 409, 한도 밖 · 빠진 값 · 없는 값 422."""
    res = client.post(url, json=body) if body is not None else client.post(url)
    assert res.status_code == status_code, res.text
