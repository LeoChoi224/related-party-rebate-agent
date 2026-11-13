/**
 * 작업 표와 상태 변경 버튼.
 * 버튼은 작업 상태로 고른다(열림 → 진행 · 완료, 진행 → 완료). 허용 여부의 최종 판단은 서버(409)가 한다.
 */
import { Link } from 'react-router'
import { TaskStatus } from '../types/enums.ts'
import type { TaskItem } from '../types/task.ts'
import { formatDateTime } from '../utils/format.ts'

// 작업 상태마다 누를 수 있는 다음 상태. 백엔드 TASK_TRANSITIONS 와 같은 모양이다.
const NEXT: Record<TaskStatus, readonly TaskStatus[]> = {
  열림: [TaskStatus.IN_PROGRESS, TaskStatus.DONE],
  진행: [TaskStatus.DONE],
  완료: [],
}

type Props = {
  tasks: TaskItem[]
  busy: boolean
  onChange: (taskId: number, status: TaskStatus) => void
}

export default function TaskList({ tasks, busy, onChange }: Props) {
  if (tasks.length === 0) {
    return <p className="muted">작업이 없습니다.</p>
  }
  return (
    <div className="table-scroll">
      <table className="claim-table">
        <thead>
          <tr>
            <th>작업</th>
            <th>건 ID</th>
            <th>부서</th>
            <th>할 일</th>
            <th>생긴 이유</th>
            <th>상태</th>
            <th>열린 시각</th>
            <th>닫힌 시각</th>
            <th>처리</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => (
            <tr key={task.task_id}>
              <td>{task.task_id}</td>
              <td>
                <Link to={`/claims/${task.ref_id}`}>{task.ref_id}</Link>
              </td>
              <td>{task.dept}</td>
              <td>{task.task_type}</td>
              <td>{task.detail}</td>
              <td>{task.status}</td>
              <td>{formatDateTime(task.created_at)}</td>
              <td>{task.closed_at === null ? '—' : formatDateTime(task.closed_at)}</td>
              <td>
                <div className="actions">
                  {NEXT[task.status].map((next) => (
                    <button
                      key={next}
                      type="button"
                      className="small"
                      disabled={busy}
                      onClick={() => onChange(task.task_id, next)}
                    >
                      {next}
                    </button>
                  ))}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
