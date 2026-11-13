"""감사 사후 검토(24) 테스트.

원본 1~5월에 영업지원팀 전결로 지급된 G1 15건(22,238,349원)이 지금 그룹으로 다시 판정하면
영업임원 결재 대상이었음을 찾고, 건마다 내부감사 사후 검토 작업을 연다.
달마다 G1 합산: 4,870,186 · 4,540,341 · 4,055,114 · 4,267,112 · 4,505,596원.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import make_engine
from app.main import create_app
from app.models import RebateClaim, Task
from app.services.approval import InsufficientAuthorityError
from app.services.retro_review import RETRO_TASK, run_retro_review

AUDIT = {"actor": "최감사", "role": "내부감사"}
G1 = {"D-011", "D-024", "D-037"}
MONTH_SUMS = {
    "2026-01": 4_870_186,
    "2026-02": 4_540_341,
    "2026-03": 4_055_114,
    "2026-04": 4_267_112,
    "2026-05": 4_505_596,
}


def test_finds_g1_fifteen_claims_paid_under_support_authority(seeded_engine):
    """원본 지급 196건을 다시 판정하면 위반은 G1 15건 22,238,349원뿐이고, 판정 컬럼은 건드리지 않는다."""
    with Session(seeded_engine) as session, session.begin():
        result = run_retro_review(session, **AUDIT)
        assert (result.checked, len(result.findings), result.total_krw) == (
            196,
            15,
            22_238_349,
        )
        assert result.periods == list(MONTH_SUMS)
        assert {f.agency_id for f in result.findings} == G1
        assert {(f.period_ym, f.group_sum_krw) for f in result.findings} == set(
            MONTH_SUMS.items()
        )
        assert {
            (f.group_label, f.min_authority, f.original_approver)
            for f in result.findings
        } == {("G1", "영업임원", "영업지원팀")}
        # 06 결정: 1~5월 건의 판정 당시 값은 채우지 않는다.
        assert (
            session.scalar(
                select(func.count())
                .select_from(RebateClaim)
                .where(RebateClaim.min_authority.is_not(None))
            )
            == 0
        )


def test_opens_one_audit_task_per_claim_and_is_idempotent(seeded_engine):
    """위반 건마다 내부감사 작업이 하나씩 열리고, 다시 실행하면 같은 위반을 돌려주되 작업은 늘지 않는다."""
    with Session(seeded_engine) as session, session.begin():
        first = run_retro_review(session, **AUDIT)
        assert first.created_tasks == 15
        tasks = session.scalars(select(Task).order_by(Task.task_id)).all()
        assert {(t.dept, t.task_type, t.status, t.trigger_status) for t in tasks} == {
            ("내부감사", RETRO_TASK, "열림", None)
        }
        assert sorted(t.ref_id for t in tasks) == [f.rebate_id for f in first.findings]
        detail = tasks[0].detail
        assert "G1 합산 4,870,186원 > 한도 2,000,000원" in detail
        assert "실제 영업지원팀 전결" in detail

        second = run_retro_review(session, **AUDIT)
        assert (len(second.findings), second.created_tasks) == (15, 0)
        assert all(f.task_id is None for f in second.findings)
        assert session.scalar(select(func.count()).select_from(Task)) == 15


@pytest.mark.parametrize("role", ["영업지원팀", "영업임원", "재무", "시연 관리자"])
def test_only_audit_runs_review(seeded_engine, role):
    with Session(seeded_engine) as session, pytest.raises(InsufficientAuthorityError):
        run_retro_review(session, actor="누군가", role=role)


def test_api_runs_review_and_tasks_show_for_audit(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    with TestClient(create_app(tmp_path / "missing", engine=engine)) as client:
        res = client.post("/api/audit/retro-review", json=AUDIT)
        assert res.status_code == 200
        body = res.json()
        assert (body["total_krw"], body["created_tasks"]) == (22_238_349, 15)
        assert body["findings"][0]["original_payment_date"] is not None
        audit_tasks = client.get("/api/tasks", params={"dept": "내부감사"}).json()
        assert len(audit_tasks) == 15

        denied = client.post(
            "/api/audit/retro-review", json={"actor": "이재무", "role": "재무"}
        )
        assert denied.status_code == 403 and "내부감사만" in denied.json()["detail"]
        assert (
            client.post("/api/audit/retro-review", json={"actor": "최감사"}).status_code
            == 422
        )
    engine.dispose()
