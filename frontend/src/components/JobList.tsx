import { CaretRight } from '@phosphor-icons/react'
import { Link } from 'react-router'
import type { Job, Project } from '../api/types'
import { formatScore, formatShortDate } from '../lib/format'
import { conditionSummary } from '../lib/labels'
import { paths } from '../lib/paths'
import styles from './JobList.module.css'
import { StatusLabel } from './StatusLabel'

interface JobListProps {
  workspaceId: string
  jobs: Job[]
  /** 있으면 조립 경로 앞에 프로젝트(블록) 이름도 보여 준다 (여러 프로젝트를 섞어 보여 줄 때). */
  projects?: Project[]
}

/** 메일 앱 같은 작업 목록. 워크스페이스 홈(여러 프로젝트)에서도 쓴다. */
export function JobList({ workspaceId, jobs, projects }: JobListProps) {
  const projectName = (id: string) => projects?.find((project) => project.id === id)?.name
  return (
    <ul className={styles.list}>
      {jobs.map((job) => (
        <li key={job.id}>
          <Link className={styles.row} to={paths.job(workspaceId, job.project_id, job.id)}>
            <span className={styles.title}>
              <span className={styles.name}>{job.name}</span>
              <span className={styles.path}>
                {projects && <span className={styles.project}>{projectName(job.project_id)}</span>}
                {job.assembly_path ?? '조립 경로 없음'}
              </span>
            </span>
            <span className={styles.status}>
              <StatusLabel status={job.status} />
            </span>
            <span className={styles.condition}>
              {job.welding_condition ? conditionSummary(job.welding_condition) : ''}
            </span>
            <span className={styles.score}>
              {job.confidence && (
                <>
                  {formatScore(job.confidence.overall)}
                  <span className={styles.unit}>%</span>
                  <span className="visually-hidden"> 신뢰도</span>
                </>
              )}
            </span>
            <time className={styles.date} dateTime={job.created_at}>
              {formatShortDate(job.created_at)}
            </time>
            <CaretRight className={styles.chevron} size={14} weight="bold" aria-hidden="true" />
          </Link>
        </li>
      ))}
    </ul>
  )
}

