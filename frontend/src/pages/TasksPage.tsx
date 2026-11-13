/**
 * 부서별 작업 페이지.
 * 처음에는 역할의 기본 부서(RoleContext 의 dept)와 열림 · 진행 작업만 보여 준다.
 * 작업 상태를 바꾸면 목록을 서버에서 다시 읽는다. 감사 사후 검토 작업은 24 에서 생긴다.
 */
import { useEffect, useState } from 'react'
import { ApiError } from '../api/client.ts'
import { changeTaskStatus, listTasks } from '../api/tasks.ts'
import TaskList from '../components/TaskList.tsx'
import { useRole } from '../context/RoleContext.tsx'
import { Department, TaskStatus } from '../types/enums.ts'
import type { TaskItem } from '../types/task.ts'

const DEPARTMENTS = Object.values(Department)
// 할 일만 볼 때의 상태. "완료 포함"이면 거르지 않는다(빈 배열).
const TODO_STATUSES = [TaskStatus.OPEN, TaskStatus.IN_PROGRESS] as const

/** 선택 상자 값(string)이 부서 3개 중 하나인지 확인한다. 빈 글자("전체")면 null. */
function findDepartment(value: string): Department | null {
  return DEPARTMENTS.find((dept) => dept === value) ?? null
}

export default function TasksPage() {
  const { role, dept } = useRole()
  // 역할이 바뀌면 같은 주소여도 새로 만들어, 부서 필터가 새 역할의 기본값으로 돌아간다(13 과 같음).
  return <TasksView key={role} initialDept={dept} />
}

function TasksView({ initialDept }: { initialDept: Department | null }) {
  const [dept, setDept] = useState<Department | null>(initialDept)
  const [includeDone, setIncludeDone] = useState(false)
  const [tasks, setTasks] = useState<TaskItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false
    listTasks(dept, includeDone ? [] : TODO_STATUSES)
      .then((items) => {
        if (ignore) return
        setTasks(items)
        setError(null)
      })
      .catch((e: unknown) => {
        if (ignore) return
        setError(e instanceof ApiError ? e.message : `요청을 보내지 못했습니다: ${String(e)}`)
      })
    return () => {
      ignore = true
    }
  }, [dept, includeDone, reloadKey])

  /** 작업 상태를 바꾸고, 성공하면 다시 읽고, 실패하면 서버 문장을 남긴다(14 의 run 과 같음). */
  async function change(taskId: number, status: TaskStatus) {
    setBusy(true)
    setActionError(null)
    try {
      await changeTaskStatus(taskId, status)
      setReloadKey((key) => key + 1)
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : `요청을 보내지 못했습니다: ${String(e)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <h2>작업 목록</h2>
      <div className="toolbar">
        <label>
          부서{' '}
          <select
            value={dept ?? ''}
            onChange={(event) => setDept(findDepartment(event.target.value))}
          >
            <option value="">전체</option>
            {DEPARTMENTS.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={includeDone}
            onChange={(event) => setIncludeDone(event.target.checked)}
          />
          완료 포함
        </label>
        {tasks !== null && <span>{tasks.length}건</span>}
      </div>

      {error !== null && <p className="error">{error}</p>}
      {actionError !== null && <p className="error">{actionError}</p>}
      {tasks === null ? (
        error === null && <p>불러오는 중…</p>
      ) : (
        <TaskList tasks={tasks} busy={busy} onChange={(id, status) => void change(id, status)} />
      )}
      <p className="muted">
        상태가 바뀌어 생긴 작업(지급 실행 등)은 건을 처리하면 자동으로 닫힙니다. 손으로 닫을 수 있는
        것은 정황 소명 요청처럼 상태 전이와 상관없이 생긴 작업뿐입니다.
      </p>
    </section>
  )
}
