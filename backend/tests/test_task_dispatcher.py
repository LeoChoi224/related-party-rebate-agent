"""부서별 작업 테스트.

앞부분은 규칙표 · 배정 · 자동 완료를 원본 6월분 접수 뒤에 보고,
뒷부분은 작업 API(목록 · 상태 변경)를 본다.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import make_engine
from app.main import create_app
from app.models import EventLog, RebateClaim, Task
from app.models.enums import ClaimStatus as S
from app.models.enums import Decision, Department, TaskStatus
from app.services.approval import decide_approval, decide_claim
from app.services.claim_state import transition
from app.services.intake import intake_period
from app.services.task_dispatcher import (
    InvalidTaskTransitionError,
    change_task_status,
    find_rule,
)

G1_CLAIMS = ["RB-00054", "RB-00120", "RB-00180"]
D001_JUNE = "RB-00006"
# 원본 6월분 D-034 · D-041 건(정황 관계).
CIRCUMSTANTIAL = ["RB-00168", "RB-00198"]
EXECUTIVE = {"actor": "박임원", "role": "영업임원"}
SUPPORT = {"actor": "김지원", "role": "영업지원팀"}
SYSTEM = {"actor": "시스템", "actor_role": "시스템"}


@pytest.fixture
def june_engine(seeded_engine):
    """원본으로 채우고 6월분을 접수까지 마친 임시 DB."""
    with Session(seeded_engine) as session, session.begin():
        intake_period(session, "2026-06")
    return seeded_engine


def tasks_of(session: Session, rebate_id: str) -> list[Task]:
    return session.scalars(
        select(Task).where(Task.ref_id == rebate_id).order_by(Task.task_id)
    ).all()


def count_tasks(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Task))


@pytest.mark.parametrize(
    ("from_status", "to_status", "expected"),
    [
        ("상신대기", "승인", (Department.FINANCE, "지급 실행")),
        ("전결대기", "승인", (Department.FINANCE, "지급 실행")),
        # 정확한 짝이 '아무거나' 규칙보다 먼저다.
        ("소명대기", "지급보류", (Department.SALES_SUPPORT, "추가 소명 요청")),
        ("지급지시", "지급보류", (Department.FINANCE, "지급 계좌 확인")),
        ("관계확인", "소명대기", (Department.SALES_SUPPORT, "소명 요청")),
        ("승인", "재검토필요", (Department.SALES_SUPPORT, "재판정")),
        # 결재 대기 · 접수 흐름은 작업이 아니다.
        ("접수", "관계확인", None),
        ("관계확인", "상신대기", None),
        ("승인", "지급지시", None),
    ],
)
def test_find_rule(from_status, to_status, expected):
    assert find_rule(from_status, to_status) == expected


def test_intake_opens_only_circumstantial_tasks(june_engine):
    """6월 접수 직후 작업은 정황 2건(영업지원팀 소명 요청)뿐이다. 지급은 막지 않는다."""
    with Session(june_engine) as session:
        tasks = session.scalars(select(Task).order_by(Task.task_id)).all()
        assert [(t.ref_id, t.dept, t.task_type) for t in tasks] == [
            ("RB-00168", "영업지원팀", "소명 요청"),
            ("RB-00198", "영업지원팀", "소명 요청"),
        ]
        assert {t.detail for t in tasks} == {"D-034–D-041 대표자 일치(정황)"}
        assert {(t.trigger_status, t.created_by_event) for t in tasks} == {(None, None)}
        assert [session.get(RebateClaim, r).status for r in CIRCUMSTANTIAL] == [
            "전결대기",
            "전결대기",
        ]


def test_executive_approval_opens_finance_tasks(june_engine):
    """로드맵 10 완료 기준: G1 승인이 나면 재무 지급 실행 작업이 건마다 생긴다."""
    with Session(june_engine) as session, session.begin():
        decide_approval(session, 1, decision=Decision.APPROVE, reason="", **EXECUTIVE)

    with Session(june_engine) as session:
        for rebate_id in G1_CLAIMS:
            (task,) = tasks_of(session, rebate_id)
            assert (task.dept, task.task_type, task.status) == (
                "재무",
                "지급 실행",
                "열림",
            )
            assert task.trigger_status == "승인"
            assert task.detail == "상신대기 → 승인: 영업임원 승인"
            # 작업이 가리키는 이력은 바로 그 건의 승인 이력이다.
            event = session.get(EventLog, task.created_by_event)
            assert (event.entity_id, event.to_status) == (rebate_id, "승인")


def test_support_approval_opens_one_finance_task(june_engine):
    """전결 승인도 같은 규칙으로 재무 작업 1건을 만든다."""
    with Session(june_engine) as session, session.begin():
        decide_claim(
            session, D001_JUNE, decision=Decision.APPROVE, reason="", **SUPPORT
        )
    with Session(june_engine) as session:
        assert [(t.dept, t.task_type) for t in tasks_of(session, D001_JUNE)] == [
            ("재무", "지급 실행")
        ]


def test_rejection_opens_no_task(june_engine):
    """반려는 작업을 만들지 않는다. 다음 할 일은 21 에서 소명대기로 갈 때 생긴다."""
    with Session(june_engine) as session, session.begin():
        decide_approval(
            session, 1, decision=Decision.REJECT, reason="소명 먼저", **EXECUTIVE
        )
        assert count_tasks(session) == 2


def test_leaving_status_closes_its_task(june_engine):
    """승인 → 지급지시 로 넘어가면 그 건의 지급 실행 작업만 자동 완료된다."""
    with Session(june_engine) as session, session.begin():
        decide_approval(session, 1, decision=Decision.APPROVE, reason="", **EXECUTIVE)
        claim = session.get(RebateClaim, G1_CLAIMS[0])
        transition(session, claim, S.PAYMENT_ORDERED, reason="지급 지시", **SYSTEM)

    with Session(june_engine) as session:
        (done,) = tasks_of(session, G1_CLAIMS[0])
        assert done.status == "완료"
        assert done.closed_at is not None
        (other,) = tasks_of(session, G1_CLAIMS[1])
        assert (other.status, other.closed_at) == ("열림", None)


def test_returning_to_on_hold_keeps_only_the_new_task_open(june_engine):
    """지급보류 → 소명대기 → 지급보류 로 돌아와도 열린 작업은 지금 상태 것 하나뿐이다."""
    with Session(june_engine) as session, session.begin():
        claim = session.get(RebateClaim, D001_JUNE)
        for to_status in (S.AWAITING_EXPLANATION, S.ON_HOLD, S.AWAITING_EXPLANATION):
            transition(session, claim, to_status, reason="시험", **SYSTEM)
        transition(session, claim, S.ON_HOLD, reason="증빙 또 부족", **SYSTEM)

    with Session(june_engine) as session:
        tasks = tasks_of(session, D001_JUNE)
        assert [(t.task_type, t.status) for t in tasks] == [
            ("소명 요청", "완료"),
            ("추가 소명 요청", "완료"),
            ("소명 요청", "완료"),
            ("추가 소명 요청", "열림"),
        ]


def test_circumstantial_task_stays_open_after_approval(june_engine):
    """정황 소명 요청은 상태가 만든 작업이 아니라서, 건이 승인돼도 열린 채로 남는다."""
    with Session(june_engine) as session, session.begin():
        decide_claim(
            session, CIRCUMSTANTIAL[0], decision=Decision.APPROVE, reason="", **SUPPORT
        )
    with Session(june_engine) as session:
        tasks = tasks_of(session, CIRCUMSTANTIAL[0])
        assert [(t.task_type, t.status) for t in tasks] == [
            ("소명 요청", "열림"),
            ("지급 실행", "열림"),
        ]


def test_task_status_moves_forward_only(june_engine):
    """열림 → 진행 → 완료는 되고, 완료는 다시 열 수 없다."""
    with Session(june_engine) as session, session.begin():
        task = change_task_status(session, 1, TaskStatus.IN_PROGRESS)
        assert task.closed_at is None
        task = change_task_status(session, 1, TaskStatus.DONE)
        assert task.status == "완료"
    with (
        pytest.raises(InvalidTaskTransitionError, match="완료 → 열림"),
        Session(june_engine) as session,
    ):
        change_task_status(session, 1, TaskStatus.OPEN)


def test_unknown_task_is_lookup_error(june_engine):
    with pytest.raises(LookupError), Session(june_engine) as session:
        change_task_status(session, 99, TaskStatus.DONE)


@pytest.fixture
def api_engine(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    yield eng
    eng.dispose()


@pytest.fixture
def client(tmp_path, api_engine):
    """앱이 켜지며 원본으로 채운 뒤 6월분 접수와 G1 승인까지 마친 클라이언트."""
    with TestClient(create_app(tmp_path / "missing", engine=api_engine)) as c:
        assert c.post("/api/claims/intake", params={"period": "2026-06"}).is_success
        approve = {"decision": "승인", "reason": "", **EXECUTIVE}
        assert c.post("/api/approvals/1/decision", json=approve).is_success
        yield c


def test_api_lists_tasks_by_department(client):
    """접수 뒤 정황 2건, G1 승인 뒤 재무 6건. dept 로 부서별로 거른다.

    G1 은 승인 직후 상계검토로 넘어가(22) 지급 실행 3건이 닫히고 상계 검토 3건이 열린다.
    """
    all_tasks = client.get("/api/tasks").json()
    assert len(all_tasks) == 8
    finance = client.get("/api/tasks", params={"dept": "재무"}).json()
    assert [(t["ref_id"], t["task_type"], t["status"]) for t in finance] == [
        (rebate_id, "지급 실행", "완료") for rebate_id in G1_CLAIMS
    ] + [(rebate_id, "상계 검토", "열림") for rebate_id in G1_CLAIMS]
    support = client.get("/api/tasks", params={"dept": "영업지원팀"}).json()
    assert [t["ref_id"] for t in support] == CIRCUMSTANTIAL
    assert support[0]["detail"] == "D-034–D-041 대표자 일치(정황)"


def test_api_task_moves_open_progress_done_then_409(client):
    """열림 → 진행 → 완료는 200, 완료를 다시 열면 409. 손으로 닫는 정황 소명 작업(1번)으로 본다."""
    res = client.patch("/api/tasks/1", json={"status": "진행"})
    assert (res.status_code, res.json()["status"]) == (200, "진행")
    assert client.get("/api/tasks", params={"status": "진행"}).json()[0]["task_id"] == 1

    res = client.patch("/api/tasks/1", json={"status": "완료"})
    assert res.status_code == 200
    assert res.json()["closed_at"] is not None

    res = client.patch("/api/tasks/1", json={"status": "열림"})
    assert res.status_code == 409
    assert res.json() == {
        "detail": "작업 상태를 바꿀 수 없습니다: 완료 → 열림 (작업 1)"
    }


def test_api_transition_task_cannot_be_closed_by_hand(client):
    """G1 상계 검토 작업(6번)은 진행은 되지만, 건이 아직 상계검토라 손으로 완료하면 409."""
    assert client.patch("/api/tasks/6", json={"status": "진행"}).status_code == 200

    res = client.patch("/api/tasks/6", json={"status": "완료"})
    assert res.status_code == 409
    assert res.json() == {
        "detail": "건 RB-00054 이(가) 아직 상계검토 상태라 '상계 검토' 작업을 닫을 수 없습니다. "
        "건을 처리하면 자동으로 닫힙니다 (작업 6)"
    }
    # 거절된 요청은 아무것도 바꾸지 않는다.
    task = client.get("/api/tasks", params={"status": "진행"}).json()[0]
    assert (task["task_id"], task["closed_at"]) == (6, None)


def test_api_lists_tasks_by_several_statuses(client):
    """상태를 둘 고르면 합집합이다. 완료를 빼면 할 일만 남는다."""
    client.patch("/api/tasks/1", json={"status": "완료"})
    client.patch("/api/tasks/2", json={"status": "진행"})
    todo = client.get("/api/tasks", params={"status": ["열림", "진행"]}).json()
    assert [t["task_id"] for t in todo] == [2, 6, 7, 8]
    assert len(client.get("/api/tasks").json()) == 8


def test_api_task_times_are_marked_utc(client):
    """작업 시각은 "Z" 가 붙어 나가 화면이 한국 시각으로 잘못 읽지 않는다."""
    client.patch("/api/tasks/1", json={"status": "완료"})
    task = client.get("/api/tasks", params={"status": "완료"}).json()[0]
    assert task["created_at"].endswith("Z")
    assert task["closed_at"].endswith("Z")


@pytest.mark.parametrize(
    ("method", "url", "kwargs", "status_code"),
    [
        ("patch", "/api/tasks/99", {"json": {"status": "완료"}}, 404),
        ("patch", "/api/tasks/3", {"json": {"status": "보류"}}, 422),
        ("get", "/api/tasks", {"params": {"dept": "영업"}}, 422),
    ],
)
def test_api_task_errors(client, method, url, kwargs, status_code):
    """없는 작업 404, 없는 상태 값 · 부서 이름은 422."""
    assert getattr(client, method)(url, **kwargs).status_code == status_code
