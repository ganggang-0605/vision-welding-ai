import type { JobStatus } from '../api/types'
import { JOB_STATUS_LABEL, JOB_STATUS_TONE } from '../lib/labels'

/** 작업 상태 태그 */
export function StatusPill({ status }: { status: JobStatus }) {
  return <span className={`pill pill--${JOB_STATUS_TONE[status]}`}>{JOB_STATUS_LABEL[status]}</span>
}
