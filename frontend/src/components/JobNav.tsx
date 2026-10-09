import { NavLink } from 'react-router'
import { paths } from '../lib/paths'

interface JobNavProps {
  workspaceId: string
  jobId: string
}

/** 작업 화면 탭: 해석 결과(5) · 작업자 확인(6) · 승인 요약본(7) */
export function JobNav({ workspaceId, jobId }: JobNavProps) {
  return (
    <nav className="tabs" aria-label="작업 화면">
      <NavLink end to={paths.job(workspaceId, jobId)} className="tab">
        해석 결과
      </NavLink>
      <NavLink to={paths.jobReview(workspaceId, jobId)} className="tab">
        작업자 확인
      </NavLink>
      <NavLink to={paths.jobSummary(workspaceId, jobId)} className="tab">
        승인 요약본
      </NavLink>
    </nav>
  )
}
