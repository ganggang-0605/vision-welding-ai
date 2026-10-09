import { Link, useSearchParams } from 'react-router'
import { listJobs } from '../api/jobs'
import type { Job, JobStatus } from '../api/types'
import { AsyncView } from '../components/AsyncView'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAsync } from '../hooks/useAsync'
import { useWorkspace } from '../hooks/useWorkspace'
import { formatDateTime, formatPercent } from '../lib/format'
import { JOB_STATUS_LABEL, JOB_STATUSES } from '../lib/labels'
import { paths } from '../lib/paths'

/** 와이어프레임 1 — 워크스페이스 홈: 작업 DB 표 */
export function WorkspaceHomePage() {
  const workspace = useWorkspace()
  // 상태 필터는 URL(?status=)에 둬서 새로고침·공유해도 유지되게 한다.
  const [searchParams, setSearchParams] = useSearchParams()
  const status = toJobStatus(searchParams.get('status'))
  const jobs = useAsync((signal) => listJobs(workspace.id, { status }, signal), [workspace.id, status])

  const onStatusChange = (value: string) => {
    setSearchParams(value ? { status: value } : {}, { replace: true })
  }

  return (
    <div className="page">
      <PageHeader
        title={workspace.name}
        description={
          workspace.description ??
          '이 워크스페이스에서 촬영·분석한 작업 목록입니다. 작업을 눌러 해석 결과를 확인하고 승인합니다.'
        }
        actions={
          <Link className="btn btn--primary" to={paths.newJob(workspace.id)}>
            새 작업
          </Link>
        }
      />

      <section className="section" aria-labelledby="jobs-title">
        <div className="toolbar">
          <h2 id="jobs-title" className="section-title toolbar-title">
            작업 DB
          </h2>
          <label className="choice">
            상태
            <select
              className="input input--auto"
              value={status ?? ''}
              onChange={(event) => onStatusChange(event.target.value)}
            >
              <option value="">전체</option>
              {JOB_STATUSES.map((value) => (
                <option key={value} value={value}>
                  {JOB_STATUS_LABEL[value]}
                </option>
              ))}
            </select>
          </label>
        </div>

        <AsyncView
          state={jobs}
          isEmpty={(list) => list.length === 0}
          empty={status ? '이 상태의 작업이 없습니다.' : '아직 작업이 없습니다. 새 작업에서 부재 마킹을 촬영해 보세요.'}
        >
          {(list) => <JobsTable workspaceId={workspace.id} jobs={list} />}
        </AsyncView>
      </section>
    </div>
  )
}

function JobsTable({ workspaceId, jobs }: { workspaceId: string; jobs: Job[] }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">작업명</th>
            <th scope="col">상태</th>
            <th scope="col">조립 경로</th>
            <th scope="col" className="num">
              신뢰도
            </th>
            <th scope="col">생성일</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id}>
              <td className="cell-title">
                <Link to={paths.job(workspaceId, job.id)}>{job.name}</Link>
              </td>
              <td>
                <StatusPill status={job.status} />
              </td>
              <td className="mono">{job.assembly_path ?? '—'}</td>
              <td className="num">{formatPercent(job.confidence?.overall)}</td>
              <td className="nowrap">{formatDateTime(job.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function toJobStatus(value: string | null): JobStatus | undefined {
  return JOB_STATUSES.find((status) => status === value)
}
