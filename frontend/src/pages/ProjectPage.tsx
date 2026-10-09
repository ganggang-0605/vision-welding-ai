import { Link, useSearchParams } from 'react-router'
import { listJobs } from '../api/jobs'
import type { Job, JobStatus } from '../api/types'
import { AsyncView } from '../components/AsyncView'
import { Notice } from '../components/Notice'
import { PageHeader } from '../components/PageHeader'
import { JobList } from '../components/JobList'
import { useAsync } from '../hooks/useAsync'
import { useProject } from '../hooks/useProject'
import { useWorkspace } from '../hooks/useWorkspace'
import { JOB_STATUS_LABEL, JOB_STATUSES, OPEN_STATUSES } from '../lib/labels'
import { paths } from '../lib/paths'
import styles from './ProjectPage.module.css'

/** 목록 위 필터. 해석 전·해석 중은 잠깐 지나가는 상태라 버튼으로 두지 않는다. */
const FILTERS: readonly JobStatus[] = ['needs_review', 'awaiting_approval', 'approved']

/** 프로젝트(호선) 페이지: 확인할 작업 + 메일 앱 같은 작업 목록 (와이어프레임 1의 목록) */
export function ProjectPage() {
  const workspace = useWorkspace()
  const project = useProject()
  // 상태 필터는 URL(?status=)에 둬서 새로고침·공유해도 유지되게 한다.
  const [searchParams, setSearchParams] = useSearchParams()
  const status = toJobStatus(searchParams.get('status'))
  // 제목 아래 개수와 '확인 필요' 안내에 전체 목록이 필요하므로 한 번에 받아 화면에서 거른다.
  const jobs = useAsync(
    (signal) => listJobs(workspace.id, { project_id: project.id }, signal),
    [workspace.id, project.id],
  )
  const all = jobs.data ?? []
  const openCount = all.filter((job) => OPEN_STATUSES.includes(job.status)).length
  const toReview = all.filter((job) => job.status === 'needs_review')

  const onStatusChange = (value: JobStatus | undefined) => {
    setSearchParams(value ? { status: value } : {}, { replace: true })
  }

  return (
    <div className="page">
      <PageHeader
        breadcrumb={[{ label: workspace.name, to: paths.workspaceHome(workspace.id) }, { label: project.name }]}
        title={project.name}
        description={
          <>
            {project.description && <p className={styles.description}>{project.description}</p>}
            {jobs.data && (openCount > 0 ? `진행 중인 작업 ${openCount}건` : '진행 중인 작업이 없어요')}
          </>
        }
        actions={
          <>
            <Link className="btn" to={paths.assemblyTree(workspace.id, project.id)}>
              조립 트리
            </Link>
            <Link className="btn btn--primary" to={paths.newJob(workspace.id, project.id)}>
              새 작업
            </Link>
          </>
        }
      />

      {toReview.length > 0 && <ReviewNotice workspaceId={workspace.id} projectId={project.id} jobs={toReview} />}

      <section className="section" aria-labelledby="jobs-title">
        <div className="section-head">
          <h2 id="jobs-title" className="section-title">
            모든 작업
          </h2>
          <div className="segmented" role="group" aria-label="상태로 거르기">
            <button type="button" aria-pressed={status === undefined} onClick={() => onStatusChange(undefined)}>
              전체
            </button>
            {FILTERS.map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={status === value}
                onClick={() => onStatusChange(value)}
              >
                {JOB_STATUS_LABEL[value]}
              </button>
            ))}
          </div>
        </div>

        <AsyncView
          state={jobs}
          isEmpty={(list) => !list.some((job) => !status || job.status === status)}
          empty={
            status
              ? `${JOB_STATUS_LABEL[status]} 상태인 작업이 없어요.`
              : '아직 작업이 없어요. 새 작업에서 부재 표기를 찍어 보세요.'
          }
        >
          {(list) => <JobList workspaceId={workspace.id} jobs={status ? list.filter((job) => job.status === status) : list} />}
        </AsyncView>
      </section>
    </div>
  )
}

function ReviewNotice({ workspaceId, projectId, jobs }: { workspaceId: string; projectId: string; jobs: Job[] }) {
  const [first] = jobs
  return (
    <Notice
      tone="warning"
      title={jobs.length === 1 ? `${first.name} 확인이 필요해요` : `확인이 필요한 작업이 ${jobs.length}건 있어요`}
      action={
        <Link className="btn" to={paths.jobReview(workspaceId, projectId, first.id)}>
          검토하기
        </Link>
      }
    >
      {jobs.length === 1 ? first.needs_review[0] : jobs.map((job) => job.name).join(', ')}
    </Notice>
  )
}

function toJobStatus(value: string | null): JobStatus | undefined {
  return JOB_STATUSES.find((status) => status === value)
}
