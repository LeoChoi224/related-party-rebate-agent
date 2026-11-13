/**
 * 부서별 작업 타입. 백엔드 schemas/task.py 와 맞춘다.
 */
import type { ClaimStatus, Department, TaskStatus } from './enums.ts'

/** 작업 한 건. 시각은 UTC 표시("…Z")가 붙은 ISO 글자다. */
export type TaskItem = {
  task_id: number
  dept: Department
  task_type: string
  ref_type: string
  /** 대상 장려금 건 ID */
  ref_id: string
  status: TaskStatus
  /** 이 작업을 만든 건 상태. 상태 전이가 아닌 작업(정황 소명 등)이면 null */
  trigger_status: ClaimStatus | null
  /** 생긴 이유 */
  detail: string
  created_by_event: number | null
  created_at: string
  closed_at: string | null
}

/** 작업 상태 변경 요청 본문. */
export type TaskStatusChange = {
  status: TaskStatus
}
