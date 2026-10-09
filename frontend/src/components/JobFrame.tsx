import { useEffect, type ReactNode } from 'react'
import { Link, Navigate, useLocation } from 'react-router'
import { isApiError } from '../api/client'
import { getJob } from '../api/jobs'
import type { Job } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { useRequiredParam } from '../hooks/useRequiredParam'
import { useProject } from '../hooks/useProject'
import { useWorkspace } from '../hooks/useWorkspace'
import { formatDateTime } from '../lib/format'
import { paths } from '../lib/paths'
import { AsyncView } from './AsyncView'
import { JobNav } from './JobNav'
import { Notice } from './Notice'
import { PageHeader } from './PageHeader'
import styles from './JobFrame.module.css'
import { StatusLabel } from './StatusLabel'

/** 해석(analyze · review)은 백그라운드에서 돌아서, analyzing 동안 이 간격으로 작업을 다시 읽는다 */
const ANALYSIS_POLL_MS = 2000

interface JobFrameProps {
  /** 화면 이름 (예: '해석 결과') — 브라우저 탭 제목에 쓴다. */
  section: string
  /** 작업을 불러온 뒤 그릴 본문. reload 로 작업을 다시 불러온다. */
  children: (job: Job, reload: () => void) => ReactNode
}

/** 작업 화면(5·6·7) 공통 틀: URL 의 :jobId 작업을 불러와 위치·제목·상태·화면 전환을 그린다. */
export function JobFrame(props: JobFrameProps) {
  const jobId = useRequiredParam('jobId')
  // 다른 작업으로 이동하면 상태를 새로 시작한다 (이전 작업이 잠깐 보이지 않도록).
  return <JobFrameContent key={jobId} {...props} />
}

function JobFrameContent({ section, children }: JobFrameProps) {
  const workspace = useWorkspace()
  const project = useProject()
  const { pathname } = useLocation()
  const jobId = useRequiredParam('jobId')
  const job = useAsync((signal) => getJob(workspace.id, jobId, signal), [workspace.id, jobId])
  const projectHome = paths.project(workspace.id, project.id)
  const analyzing = job.data?.status === 'analyzing'
  const { reload } = job

  // 해석이 끝날 때까지 작업을 다시 읽는다 (다시 읽을 때마다 job.data 가 바뀌어 다음 타이머가 걸림).
  useEffect(() => {
    if (!analyzing) return
    const timer = setTimeout(reload, ANALYSIS_POLL_MS)
    return () => clearTimeout(timer)
  }, [analyzing, job.data, reload])

  // 없는 작업이거나 다른 워크스페이스의 작업 (백엔드 404): 다시 시도해도 같으므로 프로젝트로 안내한다.
  if (!job.loading && isApiError(job.error, 404)) {
    return <JobNotFound projectName={project.name} projectHome={projectHome} jobId={jobId} />
  }
  // 주소의 프로젝트와 작업의 프로젝트가 다르면 (옛 링크 등) 작업이 속한 프로젝트 주소로 옮긴다.
  if (job.data && job.data.id === jobId && job.data.project_id !== project.id) {
    const prefix = paths.project(workspace.id, project.id)
    return <Navigate replace to={paths.project(workspace.id, job.data.project_id) + pathname.slice(prefix.length)} />
  }

  return (
    <div className="page">
      {/* reload(승인·재해석 후) 중에는 본문을 유지해 폼 상태·안내 문구가 사라지지 않게 한다. */}
      <AsyncView state={job} keepPreviousData>
        {(data) => (
          <>
            <PageHeader
              breadcrumb={[{ label: project.name, to: projectHome }, { label: data.name }]}
              title={data.name}
              documentTitle={`${data.name} ${section}`}
              description={
                <span className={styles.meta}>
                  <StatusLabel status={data.status} />
                  {data.assembly_path && <span className="mono">{data.assembly_path}</span>}
                  <span>{formatDateTime(data.created_at)}</span>
                </span>
              }
            />
            <JobNav workspaceId={workspace.id} projectId={project.id} jobId={data.id} />
            {data.status === 'analyzing' ? (
              <div className={styles.notice}>
                <Notice title="해석하고 있어요">사진 한 장에 10~30초쯤 걸려요. 끝나면 이 화면이 바뀌어요.</Notice>
              </div>
            ) : (
              data.analysis_error && (
                <div className={styles.notice}>
                  <Notice tone="error" title="마지막 해석이 실패해서 이전 결과를 보여 주고 있어요">
                    {data.analysis_error}
                  </Notice>
                </div>
              )
            )}
            {children(data, job.reload)}
          </>
        )}
      </AsyncView>
    </div>
  )
}

interface JobNotFoundProps {
  projectName: string
  projectHome: string
  jobId: string
}

function JobNotFound({ projectName, projectHome, jobId }: JobNotFoundProps) {
  return (
    <div className="page">
      <PageHeader
        breadcrumb={[{ label: projectName, to: projectHome }, { label: jobId }]}
        title="작업을 찾을 수 없어요"
        description={`'${jobId}' 작업이 이 워크스페이스에 없어요.`}
      />
      <p className="button-row">
        <Link className="btn btn--primary" to={projectHome}>
          작업 목록으로
        </Link>
      </p>
    </div>
  )
}
