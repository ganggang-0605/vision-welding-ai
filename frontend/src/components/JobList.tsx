import { CaretRight } from '@phosphor-icons/react'
import { Link } from 'react-router'
import type { Job } from '../api/types'
import { formatScore, formatShortDate } from '../lib/format'
import { cellSummary, conditionSummary } from '../lib/labels'
import { paths } from '../lib/paths'
import styles from './JobList.module.css'
import { StatusLabel } from './StatusLabel'

interface JobListProps {
  workspaceId: string
  jobs: Job[]
}

/** 메일 앱 같은 작업 목록 (워크스페이스 홈) */
export function JobList({ workspaceId, jobs }: JobListProps) {
  return (
    <ul className={styles.list}>
      {jobs.map((job) => (
        <li key={job.id}>
          <Link className={styles.row} to={paths.job(workspaceId, job.id)}>
            <span className={styles.title}>
              <span className={styles.name}>{job.name}</span>
              <span className={styles.path}>
                {job.assembly_path ?? '조립 경로 없음'}
              </span>
            </span>
            <span className={styles.status}>
              <StatusLabel status={job.status} />
            </span>
            <span className={styles.condition}>
              {/* 셀 형태가 있으면 그것을, 없으면 용접 조건을 한 줄로 */}
              {job.cell ? cellSummary(job.cell) : job.welding_condition ? conditionSummary(job.welding_condition) : ''}
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

