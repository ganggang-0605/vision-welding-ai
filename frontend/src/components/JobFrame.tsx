import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { isApiError } from '../api/client'
import { getJob } from '../api/jobs'
import type { Job } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { useRequiredParam } from '../hooks/useRequiredParam'
import { useWorkspace } from '../hooks/useWorkspace'
import { paths } from '../lib/paths'
import { AsyncView } from './AsyncView'
import { JobNav } from './JobNav'
import { PageHeader } from './PageHeader'
import { StatusPill } from './StatusPill'

interface JobFrameProps {
  /** 화면 이름 (예: '해석 결과') — 브라우저 탭 제목에 쓴다. */
  section: string
  /** 제목 아래 설명 */
  description: string
  /** 작업을 불러온 뒤 그릴 본문. reload 로 작업을 다시 불러온다. */
  children: (job: Job, reload: () => void) => ReactNode
}

/** 작업 화면(5·6·7) 공통 틀: URL 의 :jobId 작업을 불러와 제목·상태·탭을 그린다. */
export function JobFrame(props: JobFrameProps) {
  const jobId = useRequiredParam('jobId')
  // 다른 작업으로 이동하면 상태를 새로 시작한다 (이전 작업이 잠깐 보이지 않도록).
  return <JobFrameContent key={jobId} {...props} />
}

function JobFrameContent({ section, description, children }: JobFrameProps) {
  const workspace = useWorkspace()
  const jobId = useRequiredParam('jobId')
  const job = useAsync((signal) => getJob(workspace.id, jobId, signal), [workspace.id, jobId])

  // 없는 작업이거나 다른 워크스페이스의 작업 (백엔드 404) — 다시 시도해도 같으므로 작업 DB 로 안내한다.
  if (!job.loading && isApiError(job.error, 404)) return <JobNotFound workspaceId={workspace.id} jobId={jobId} />

  return (
    <div className="page">
      {/* reload(승인·재해석 후) 중에는 본문을 유지해 폼 상태·안내 문구가 사라지지 않게 한다. */}
      <AsyncView state={job} keepPreviousData>
        {(data) => (
          <>
            <PageHeader
              eyebrow={<Link to={paths.workspaceHome(workspace.id)}>← 작업 DB</Link>}
              title={data.name}
              documentTitle={`${section} · ${data.name}`}
              description={description}
              actions={<StatusPill status={data.status} />}
            />
            <JobNav workspaceId={workspace.id} jobId={data.id} />
            {children(data, job.reload)}
          </>
        )}
      </AsyncView>
    </div>
  )
}

function JobNotFound({ workspaceId, jobId }: { workspaceId: string; jobId: string }) {
  return (
    <div className="page">
      <PageHeader
        eyebrow={<Link to={paths.workspaceHome(workspaceId)}>← 작업 DB</Link>}
        title="작업을 찾을 수 없습니다"
        description={`'${jobId}' 작업이 이 워크스페이스에 없습니다.`}
      />
      <p className="button-row">
        <Link className="btn btn--primary" to={paths.workspaceHome(workspaceId)}>
          작업 DB 로 돌아가기
        </Link>
      </p>
    </div>
  )
}
