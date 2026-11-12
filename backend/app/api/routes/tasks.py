"""작업 API: 부서별 작업 목록, 작업 상태 변경.

작업 목록 화면(15)이 쓰고, 역할 선택(12)이 dept 를 채운다.
작업 상태 오류는 이 라우트에서만 나므로 전역 처리기 대신 여기서 409 로 바꾼다.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import SessionDep
from app.models import Task
from app.models.enums import Department, TaskStatus
from app.schemas.task import TaskOut, TaskStatusChange
from app.services.task_dispatcher import InvalidTaskTransitionError, change_task_status

router = APIRouter(prefix="/tasks", tags=["tasks"])


# 접두사 /tasks 자체가 목록 주소다. "/" 로 두면 /api/tasks 가 307 로 한 번 더 돈다.
@router.get("")
def list_tasks(
    session: SessionDep,
    dept: Department | None = None,
    status: TaskStatus | None = None,
) -> list[TaskOut]:
    """부서 · 작업 상태로 거른 작업 목록. 값을 비우면 거르지 않는다."""
    query = select(Task).order_by(Task.task_id)
    if dept is not None:
        query = query.where(Task.dept == dept)
    if status is not None:
        query = query.where(Task.status == status)
    return session.scalars(query).all()


@router.patch(
    "/{task_id}",
    responses={
        404: {"description": "작업이 없음"},
        409: {"description": "작업 상태 전이표에 없는 변경(완료는 다시 열 수 없음)"},
    },
)
def change_status(task_id: int, body: TaskStatusChange, session: SessionDep) -> TaskOut:
    """작업을 진행 · 완료로 표시한다."""
    try:
        return change_task_status(session, task_id, body.status)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except InvalidTaskTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
