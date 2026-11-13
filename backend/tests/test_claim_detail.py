"""건 상세 조회 테스트.

앞부분은 서비스(get_claim_detail)를 원본 데이터로 직접 부르고,
뒷부분은 API(GET /api/claims/{rebate_id})가 시각 표시 · 404 를 바르게 내는지 본다.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import make_engine
from app.main import create_app
from app.models.enums import BankResult, Decision
from app.services.approval import decide_approval, decide_claim
from app.services.claim_detail import get_claim_detail
from app.services.intake import intake_period
from app.services.payment import apply_bank_reply, order_payment

G1 = {"D-011", "D-024", "D-037"}
G1_JUNE = ["RB-00054", "RB-00120", "RB-00180"]
# 6월분 단독 대리점 건(D-001)과 정황 대리점 건(D-034).
STANDALONE_JUNE = "RB-00006"
CIRCUMSTANTIAL_JUNE = "RB-00168"
# D-011 의 1월분. 지급완료로 시작해 한도 판정을 한 적이 없다.
G1_JANUARY = "RB-00049"
SHARED_ACCOUNT = "국민 412-27-556310"


def detail(engine, rebate_id):
    with Session(engine) as session:
        return get_claim_detail(session, rebate_id)


@pytest.fixture
def june_received(seeded_engine):
    """6월분을 접수한 DB."""
    with Session(seeded_engine) as session, session.begin():
        intake_period(session, "2026-06")
    return seeded_engine


def test_g1_claim_explains_why_it_goes_to_executive(june_received):
    """G1 건: 구성 3건 합산 3,888,097 > 한도 2,000,000 → 영업임원, 근거와 승인 요청이 보인다."""
    d = detail(june_received, "RB-00054")
    assert d.status == "상신대기"
    assert d.group_label == "G1"
    assert d.min_authority == "영업임원"
    assert d.limit_krw == 2_000_000
    assert [c.rebate_id for c in d.unit_claims] == G1_JUNE
    assert sum(c.rebate_amount_krw for c in d.unit_claims) == d.group_sum_krw
    assert d.group_sum_krw == 3_888_097

    # 그룹 안 세 쌍이 모두 관련자이고, 공유 계좌가 근거에 나온다.
    assert len(d.evidence) == 3
    assert {e.judgement for e in d.evidence} == {"관련자"}
    assert {e.agency_a for e in d.evidence} | {e.agency_b for e in d.evidence} == G1
    values = {m.value for e in d.evidence for m in e.matched_attrs}
    assert SHARED_ACCOUNT in values
    # 근거 행은 "파일:행" 이다.
    assert all(
        ":" in ref for e in d.evidence for m in e.matched_attrs for ref in m.refs_a
    )

    assert d.approval is not None
    assert d.approval.approver_role == "영업임원"
    assert d.approval.rebate_ids == G1_JUNE
    assert d.approval.decision is None
    assert [e.to_status for e in d.events] == ["접수", "관계확인", "상신대기"]
    assert d.events[1].payload["group_sum_krw"] == 3_888_097
    assert d.payments == []


def test_standalone_claim_has_only_itself_and_no_evidence(june_received):
    """단독 대리점 건: 구성은 자기 하나, 일치 쌍 · 승인 요청 없음."""
    d = detail(june_received, STANDALONE_JUNE)
    assert d.status == "전결대기"
    assert d.group_label is None
    assert [c.rebate_id for c in d.unit_claims] == [STANDALONE_JUNE]
    assert d.group_sum_krw == d.rebate_amount_krw
    assert d.evidence == []
    assert d.approval is None


def test_circumstantial_pair_shows_on_standalone_claim(june_received):
    """정황(대표자만 일치) 대리점은 단독으로 판정되지만, 그 정황 쌍이 근거에 보인다."""
    d = detail(june_received, CIRCUMSTANTIAL_JUNE)
    assert d.min_authority == "영업지원팀"
    assert d.group_label is None
    assert len(d.evidence) == 1
    edge = d.evidence[0]
    assert (edge.agency_a, edge.agency_b) == ("D-034", "D-041")
    assert edge.judgement == "정황"
    assert edge.match_count == 1
    assert [m.attr for m in edge.matched_attrs] == ["대표자"]


def test_claim_before_intake_has_no_judgement(seeded_engine):
    """접수 전 건: 판정 · 구성 건 · 이력이 비어 있고 원본 기록은 보인다."""
    d = detail(seeded_engine, STANDALONE_JUNE)
    assert d.status == "미접수"
    assert d.original_status == "미지급"
    assert d.original_approver is None
    assert d.original_payment_date is None
    assert d.min_authority is None
    assert d.unit_claims == []
    assert d.events == []


def test_unjudged_g1_claim_still_shows_current_relations(seeded_engine):
    """1~5월 G1 건은 판정 전이라 그룹이 비어 있지만, 지금 버전의 관련자 쌍은 보인다(감사 24)."""
    d = detail(seeded_engine, G1_JANUARY)
    assert d.agency_id == "D-011"
    assert d.status == "지급완료"
    assert d.group_label is None
    assert d.unit_claims == []
    # D-011 이 낀 쌍: D-011–D-024, D-011–D-037
    assert [(e.agency_a, e.agency_b) for e in d.evidence] == [
        ("D-011", "D-024"),
        ("D-011", "D-037"),
    ]
    assert d.source_file.endswith(".csv")


def test_paid_claim_shows_payment_with_mock_bank_reply(june_received):
    """전결 승인 → 지급 지시 → 은행 회신 성공 뒤: 지급 한 줄 [모의] 와 이력 6줄."""
    with Session(june_received) as session, session.begin():
        decide_claim(
            session,
            STANDALONE_JUNE,
            decision=Decision.APPROVE,
            reason="",
            actor="김지원",
            role="영업지원팀",
        )
        order = order_payment(session, STANDALONE_JUNE, actor="이재무", role="재무")
        payment_id = order.payment_id

    d = detail(june_received, STANDALONE_JUNE)
    assert d.status == "지급지시"
    assert len(d.payments) == 1
    assert d.payments[0].status == "회신대기"
    assert d.payments[0].bank_result is None

    with Session(june_received) as session, session.begin():
        apply_bank_reply(session, payment_id, BankResult.SUCCESS)

    d = detail(june_received, STANDALONE_JUNE)
    assert d.status == "지급완료"
    payment = d.payments[0]
    assert payment.amount_krw == d.rebate_amount_krw
    assert payment.ordered_by == "이재무"
    assert (payment.bank_result, payment.bank_provenance) == ("성공", "모의")
    assert [e.to_status for e in d.events] == [
        "접수",
        "관계확인",
        "전결대기",
        "승인",
        "지급지시",
        "지급완료",
    ]


def test_decided_request_shows_decision(june_received):
    """영업임원이 승인 요청을 승인하면 요청 칸에 결정 · 결정자 · 시각이 찬다."""
    request_id = detail(june_received, "RB-00120").approval.request_id
    with Session(june_received) as session, session.begin():
        decide_approval(
            session,
            request_id,
            decision=Decision.APPROVE,
            reason="",
            actor="박임원",
            role="영업임원",
        )

    d = detail(june_received, "RB-00120")
    assert d.status == "승인"
    assert d.approval.decision == "승인"
    assert d.approval.decided_by == "박임원"
    assert d.approval.decided_at is not None
    assert d.events[-1].actor_role == "영업임원"


def test_missing_claim_is_lookup_error(seeded_engine):
    with pytest.raises(LookupError, match="RB-99999"):
        detail(seeded_engine, "RB-99999")


@pytest.fixture
def api_engine(tmp_path):
    """API 테스트용 빈 임시 DB. 앱이 켜지며 원본으로 채운다."""
    eng = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    yield eng
    eng.dispose()


@pytest.fixture
def client(tmp_path, api_engine):
    with TestClient(create_app(tmp_path / "missing", engine=api_engine)) as c:
        yield c


def test_api_detail_marks_times_as_utc(client):
    """이력 시각은 "Z" 가 붙어 나가 브라우저가 한국 시각으로 잘못 읽지 않는다."""
    client.post("/api/claims/intake", params={"period": "2026-06"})
    res = client.get("/api/claims/RB-00054")
    assert res.status_code == 200
    body = res.json()
    assert body["group_label"] == "G1"
    assert body["events"][0]["ts"].endswith("Z")


def test_api_missing_claim_is_404(client):
    res = client.get("/api/claims/RB-99999")
    assert res.status_code == 404
    assert res.json() == {"detail": "장려금 건 RB-99999 이(가) 없습니다"}
