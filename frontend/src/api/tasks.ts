/**
 * 작업 API: 부서별 작업 목록, 작업 상태 변경.
 */
import type { Department, TaskStatus } from '../types/enums.ts'
import type { TaskItem, TaskStatusChange } from '../types/task.ts'
import { api } from './client.ts'

/** 부서 · 상태로 거른 작업 목록(작업 번호 순). 부서 null · 상태 빈 배열이면 거르지 않는다. */
export function listTasks(
  dept: Department | null,
  statuses: readonly TaskStatus[],
): Promise<TaskItem[]> {
  const params = new URLSearchParams()
  if (dept !== null) {
    params.set('dept', dept)
  }
  // 서버는 ?status=열림&status=진행 처럼 같은 이름을 여러 번 받는다(13 의 listClaims 와 같음).
  for (const status of statuses) {
    params.append('status', status)
  }
  const query = params.toString()
  return api.get<TaskItem[]>(query === '' ? '/tasks' : `/tasks?${query}`)
}

/** 작업을 진행 · 완료로 표시한다. 허용되지 않은 변경 · 전이 작업 손 완료는 409. */
export function changeTaskStatus(taskId: number, status: TaskStatus): Promise<TaskItem> {
  const body: TaskStatusChange = { status }
  return api.patch<TaskItem>(`/tasks/${taskId}`, body)
}
