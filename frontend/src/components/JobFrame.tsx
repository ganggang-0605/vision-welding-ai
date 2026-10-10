import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { isApiError } from '../api/client'
import { approveJob, getJob } from '../api/jobs'
import type { Job } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { useRequiredParam } from '../hooks/useRequiredParam'
import { useWorkspaceContext } from '../hooks/useWorkspace'
import { formatDateTime } from '../lib/format'
import { APPROVABLE_STATUSES } from '../lib/labels'
import { paths } from '../lib/paths'
import { AnalysisProgress } from './AnalysisProgress'
import { AsyncView } from './AsyncView'
import { JobNav } from './JobNav'
import { ErrorNotice, Notice } from './Notice'
import { PageHeader } from './PageHeader'
import styles from './JobFrame.module.css'
import { StatusLabel } from './StatusLabel'

/** 해석(analyze · review)은 백그라운드에서 돌아서, analyzing 동안 이 간격으로 작업을 다시 읽는다 (진행 단계도 같이) */
const ANALYSIS_POLL_MS = 1000

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
  const { workspace, me } = useWorkspaceContext()
  const jobId = useRequiredParam('jobId')
  const job = useAsync((signal) => getJob(workspace.id, jobId, signal), [workspace.id, jobId])
  const home = paths.workspaceHome(workspace.id)
  const analyzing = job.data?.status === 'analyzing'
  const { reload } = job
  const [approving, setApproving] = useState(false)
  const [approveError, setApproveError] = useState<unknown>()

  // 신뢰도 기준 미만(확인 필요)·승인 대기 작업은 어느 탭에서든 [승인] 한 번으로 작업 완료.
  // 버튼을 누르는 것이 확인 항목을 봤다는 뜻 (백엔드 acknowledge_review). 승인자는 지금 계정
  const approve = async () => {
    setApproving(true)
    setApproveError(undefined)
    try {
      await approveJob(workspace.id, jobId, { approved_by: me?.name ?? '작업자', acknowledge_review: true })
      reload()
    } catch (err) {
      setApproveError(err)
    } finally {
      setApproving(false)
    }
  }

  // 해석이 끝날 때까지 작업을 다시 읽는다 (다시 읽을 때마다 job.data 가 바뀌어 다음 타이머가 걸림).
  useEffect(() => {
    if (!analyzing) return
    const timer = setTimeout(reload, ANALYSIS_POLL_MS)
    return () => clearTimeout(timer)
  }, [analyzing, job.data, reload])

  // 없는 작업이거나 다른 워크스페이스의 작업 (백엔드 404): 다시 시도해도 같으므로 작업 목록으로 안내한다.
  if (!job.loading && isApiError(job.error, 404)) {
    return <JobNotFound workspaceName={workspace.name} home={home} jobId={jobId} />
  }

  return (
    <div className="page">
      {/* reload(승인·재해석 후) 중에는 본문을 유지해 폼 상태·안내 문구가 사라지지 않게 한다. */}
      <AsyncView state={job} keepPreviousData>
        {(data) => (
          <>
            <PageHeader
              breadcrumb={[{ label: '작업', to: home }, { label: data.name }]}
              title={data.name}
              documentTitle={`${data.name} ${section}`}
              actions={
                APPROVABLE_STATUSES.includes(data.status) && (
                  <button type="button" className="btn btn--primary" onClick={approve} disabled={approving}>
                    {approving ? '승인하는 중' : '승인'}
                  </button>
                )
              }
              description={
                <span className={styles.meta}>
                  <StatusLabel status={data.status} />
                  {data.assembly_path && <span className="mono">{data.assembly_path}</span>}
                  <span>{formatDateTime(data.created_at)}</span>
                </span>
              }
            />
            <JobNav workspaceId={workspace.id} jobId={data.id} />
            {approveError !== undefined && (
              <div className={styles.notice}>
                <ErrorNotice error={approveError} />
              </div>
            )}
            {data.status === 'analyzing' ? (
              <div className={styles.notice}>
                <AnalysisProgress job={data} />
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
  workspaceName: string
  home: string
  jobId: string
}

function JobNotFound({ workspaceName, home, jobId }: JobNotFoundProps) {
  return (
    <div className="page">
      <PageHeader
        breadcrumb={[{ label: workspaceName, to: home }, { label: jobId }]}
        title="작업을 찾을 수 없어요"
        description={`'${jobId}' 작업이 이 워크스페이스에 없어요.`}
      />
      <p className="button-row">
        <Link className="btn btn--primary" to={home}>
          작업 목록으로
        </Link>
      </p>
    </div>
  )
}
