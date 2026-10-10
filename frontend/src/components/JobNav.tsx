import { NavLink } from 'react-router'
import { paths } from '../lib/paths'

interface JobNavProps {
  workspaceId: string
  jobId: string
}

/** 작업 화면 전환 (세그먼트 컨트롤): 해석 결과(5), 해석 과정(1·2·3단계), 작업자 확인(6), 승인 요약본(7) */
export function JobNav({ workspaceId, jobId }: JobNavProps) {
  return (
    <nav className="segmented" aria-label="작업 화면">
      <NavLink end to={paths.job(workspaceId, jobId)}>
        해석 결과
      </NavLink>
      <NavLink to={paths.jobProcess(workspaceId, jobId)}>
        해석 과정
      </NavLink>
      <NavLink to={paths.jobReview(workspaceId, jobId)}>
        작업자 확인
      </NavLink>
      <NavLink to={paths.jobSummary(workspaceId, jobId)}>
        요약본
      </NavLink>
    </nav>
  )
}
