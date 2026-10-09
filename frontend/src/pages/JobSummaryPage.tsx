import { useId, useState, type FormEvent } from 'react'
import { isApiError } from '../api/client'
import { approveJob, exportJob } from '../api/jobs'
import type { Job } from '../api/types'
import { AsyncView } from '../components/AsyncView'
import { JobFrame } from '../components/JobFrame'
import { ErrorNotice, Notice } from '../components/Notice'
import { useAsync } from '../hooks/useAsync'
import { useWorkspace } from '../hooks/useWorkspace'
import { downloadJson } from '../lib/download'
import { formatDateTime, formatPercent } from '../lib/format'
import { APPROVABLE_STATUSES } from '../lib/labels'

/** 와이어프레임 7 — 승인 요약본 · 로봇 연계 JSON 내보내기 */
export function JobSummaryPage() {
  return (
    <JobFrame
      section="승인 요약본"
      description="최종 해석 결과를 요약해 승인하고, 승인된 결과를 로봇 제어·용접 프로그램용 JSON으로 내보냅니다."
    >
      {(job, reload) => (
        <>
          <Summary job={job} />
          {APPROVABLE_STATUSES.includes(job.status) && <ApproveForm job={job} onApproved={reload} />}
          <ExportSection job={job} />
        </>
      )}
    </JobFrame>
  )
}

function Summary({ job }: { job: Job }) {
  const condition = job.welding_condition
  return (
    <section className="section">
      <h2 className="section-title">요약</h2>
      <dl className="props">
        <dt>조립 경로</dt>
        <dd className="mono">{job.assembly_path ?? '—'}</dd>
        <dt>해석</dt>
        <dd>{job.marking?.interpretation ?? '—'}</dd>
        <dt>용접 조건</dt>
        <dd>
          {condition
            ? `${condition.joint_type} · ${condition.process} · ${condition.position} · ${condition.current_a} A · ${condition.voltage_v} V · ${condition.speed_cm_min} cm/min`
            : '—'}
        </dd>
        <dt>종합 신뢰도</dt>
        <dd>{formatPercent(job.confidence?.overall)}</dd>
        <dt>승인</dt>
        <dd>{job.approved_by ? `${job.approved_by} · ${formatDateTime(job.approved_at)}` : '승인 전'}</dd>
      </dl>
    </section>
  )
}

function ApproveForm({ job, onApproved }: { job: Job; onApproved: () => void }) {
  const workspace = useWorkspace()
  const inputId = useId()
  // TODO(인증): 로그인 기능이 생기면 현재 사용자로 채운다.
  const [approvedBy, setApprovedBy] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<unknown>()

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError(undefined)
    try {
      await approveJob(workspace.id, job.id, { approved_by: approvedBy.trim() })
      onApproved()
    } catch (err) {
      setError(err)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="section">
      <h2 className="section-title">승인</h2>
      <form className="form" onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor={inputId} className="field-label">
            승인자
          </label>
          <input
            id={inputId}
            className="input"
            required
            placeholder="이름"
            value={approvedBy}
            onChange={(event) => setApprovedBy(event.target.value)}
          />
        </div>
        {error !== undefined && <ErrorNotice error={error} />}
        <p className="button-row">
          <button type="submit" className="btn btn--primary" disabled={submitting || !approvedBy.trim()}>
            {submitting ? '승인 중…' : '이 해석으로 승인'}
          </button>
        </p>
      </form>
    </section>
  )
}

function ExportSection({ job }: { job: Job }) {
  const workspace = useWorkspace()
  // 승인되면(status 변경) 다시 불러온다.
  const exported = useAsync((signal) => exportJob(workspace.id, job.id, signal), [workspace.id, job.id, job.status])

  return (
    <section className="section">
      <h2 className="section-title">로봇 연계 JSON</h2>
      {isApiError(exported.error, 409) ? (
        <Notice tone="info">승인된 작업만 내보낼 수 있습니다. 승인하면 로봇 연계용 JSON이 여기에 표시됩니다.</Notice>
      ) : (
        <AsyncView state={exported}>
          {(data) => (
            <>
              <p className="button-row">
                <button type="button" className="btn btn--primary" onClick={() => downloadJson(`${data.job_id}.json`, data)}>
                  JSON 다운로드
                </button>
              </p>
              <pre className="code-block">{JSON.stringify(data, null, 2)}</pre>
            </>
          )}
        </AsyncView>
      )}
    </section>
  )
}
