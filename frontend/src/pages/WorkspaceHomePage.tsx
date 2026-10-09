import { Cube, CaretRight, UserPlus } from '@phosphor-icons/react'
import { Link } from 'react-router'
import { listJobs } from '../api/jobs'
import type { Job, Project } from '../api/types'
import { AsyncView } from '../components/AsyncView'
import { JobList } from '../components/JobList'
import { Notice } from '../components/Notice'
import { PageHeader } from '../components/PageHeader'
import { useAsync } from '../hooks/useAsync'
import { useWorkspaceContext } from '../hooks/useWorkspace'
import { OPEN_STATUSES } from '../lib/labels'
import { paths } from '../lib/paths'
import styles from './WorkspaceHomePage.module.css'

/** 홈의 '최근 작업' 개수 */
const RECENT_COUNT = 5

/** 와이어프레임 1 — 워크스페이스 홈 (노션 홈처럼): 프로젝트(블록) 목록, 확인할 작업, 최근 작업 */
export function WorkspaceHomePage() {
  const { workspace, projects } = useWorkspaceContext()
  const jobs = useAsync((signal) => listJobs(workspace.id, {}, signal), [workspace.id])

  return (
    <div className="page">
      <PageHeader
        title={workspace.name}
        description={
          workspace.kind === 'personal' ? '개인 워크스페이스' : `팀 워크스페이스, 멤버 ${workspace.member_count}명`
        }
        actions={
          <Link className="btn btn--primary" to={paths.newProject(workspace.id)}>
            새 블록
          </Link>
        }
      />

      {workspace.kind === 'personal' && (
        <Notice
          title="혼자 쓰는 워크스페이스예요"
          action={
            <Link className="btn" to={`${paths.settings(workspace.id)}#members`}>
              <UserPlus size={15} aria-hidden="true" />
              팀원 초대
            </Link>
          }
        >
          팀원을 초대하면 팀 워크스페이스로 바뀌고, 블록과 사전을 함께 써요.
        </Notice>
      )}

      <section className="section" aria-labelledby="projects-title">
        <h2 id="projects-title" className="section-title">
          블록
        </h2>
        {projects.length === 0 ? (
          <p className="state">
            아직 블록이 없어요. <Link to={paths.newProject(workspace.id)}>블록을 추가</Link>하면 작업과 조립 트리를
            블록별로 나눠 관리해요.
          </p>
        ) : (
          <ProjectList workspaceId={workspace.id} projects={projects} jobs={jobs.data} />
        )}
      </section>

      <AsyncView state={jobs}>
        {(list) => {
          const toReview = list.filter((job) => job.status === 'needs_review')
          return (
            <>
              {toReview.length > 0 && (
                <section className="section" aria-labelledby="review-title">
                  <h2 id="review-title" className="section-title">
                    확인이 필요한 작업
                  </h2>
                  <JobList workspaceId={workspace.id} jobs={toReview} projects={projects} />
                </section>
              )}
              {list.length > 0 && (
                <section className="section" aria-labelledby="recent-title">
                  <h2 id="recent-title" className="section-title">
                    최근 작업
                  </h2>
                  <JobList workspaceId={workspace.id} jobs={list.slice(0, RECENT_COUNT)} projects={projects} />
                </section>
              )}
            </>
          )
        }}
      </AsyncView>
    </div>
  )
}

interface ProjectListProps {
  workspaceId: string
  projects: Project[]
  /** 워크스페이스 전체 작업 (불러오기 전이면 undefined). 프로젝트별 개수를 센다. */
  jobs: Job[] | undefined
}

function ProjectList({ workspaceId, projects, jobs }: ProjectListProps) {
  return (
    <ul className={styles.projects}>
      {projects.map((project) => {
        const mine = jobs?.filter((job) => job.project_id === project.id)
        const open = mine?.filter((job) => OPEN_STATUSES.includes(job.status)).length ?? 0
        const review = mine?.filter((job) => job.status === 'needs_review').length ?? 0
        return (
          <li key={project.id}>
            <Link className={styles.project} to={paths.project(workspaceId, project.id)}>
              <span className={styles.icon} aria-hidden="true">
                <Cube size={20} />
              </span>
              <span className={styles.text}>
                <span className={styles.name}>{project.name}</span>
                <span className={styles.meta}>
                  {mine === undefined
                    ? project.description
                    : mine.length === 0
                      ? '작업 없음'
                      : `작업 ${mine.length}건, 진행 중 ${open}건`}
                </span>
              </span>
              {review > 0 && <span className="status status--attention">확인 필요 {review}건</span>}
              <CaretRight className={styles.chevron} size={14} weight="bold" aria-hidden="true" />
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
