import { useState } from 'react'
import type { JobStatus } from '../api/types'
import { ATTENTION_STATUSES, JOB_STATUS_LABEL } from '../lib/labels'

/**
 * 작업 상태. 색 태그 대신 글자로 쓰고, 확인이 필요한 상태는 주황, 승인된 상태는 초록으로 강조한다.
 * 보고 있는 동안 승인으로 바뀌면 한 번 튀어 오르게 한다 (처음부터 승인된 작업은 그대로).
 */
export function StatusLabel({ status }: { status: JobStatus }) {
  // 처음 그릴 때의 상태. 승인 전이었다가 승인되면 애니메이션 클래스를 붙인다 (클래스가 붙는 순간 한 번 돎).
  const [initial] = useState(status)
  const justApproved = status === 'approved' && initial !== 'approved'

  const className = ATTENTION_STATUSES.includes(status)
    ? 'status status--attention'
    : status === 'approved'
      ? `status status--done${justApproved ? ' status--done-enter' : ''}`
      : 'status'
  return <span className={className}>{JOB_STATUS_LABEL[status]}</span>
}
