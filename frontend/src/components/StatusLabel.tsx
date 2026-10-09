import type { JobStatus } from '../api/types'
import { ATTENTION_STATUSES, JOB_STATUS_LABEL } from '../lib/labels'

/** 작업 상태. 색 태그 대신 글자로 쓰고, 확인이 필요한 상태만 주황으로 강조한다. */
export function StatusLabel({ status }: { status: JobStatus }) {
  const attention = ATTENTION_STATUSES.includes(status)
  return <span className={attention ? 'status status--attention' : 'status'}>{JOB_STATUS_LABEL[status]}</span>
}
