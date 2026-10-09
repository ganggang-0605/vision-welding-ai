/** 화면 URL 생성기. 링크는 문자열을 직접 조합하지 말고 여기서 만든다 (경로 파라미터 인코딩 포함). */
import { generatePath } from 'react-router'

/** 앱을 처음 열 때 들어가는 워크스페이스 (백엔드 시드 데이터) */
export const DEFAULT_WORKSPACE_ID = 'demo'

export const paths = {
  newWorkspace: () => '/workspaces/new',
  workspaceHome: (workspaceId: string) => generatePath('/w/:workspaceId', { workspaceId }),
  newJob: (workspaceId: string) => generatePath('/w/:workspaceId/jobs/new', { workspaceId }),
  job: (workspaceId: string, jobId: string) => generatePath('/w/:workspaceId/jobs/:jobId', { workspaceId, jobId }),
  jobReview: (workspaceId: string, jobId: string) =>
    generatePath('/w/:workspaceId/jobs/:jobId/review', { workspaceId, jobId }),
  jobSummary: (workspaceId: string, jobId: string) =>
    generatePath('/w/:workspaceId/jobs/:jobId/summary', { workspaceId, jobId }),
  symbols: (workspaceId: string) => generatePath('/w/:workspaceId/symbols', { workspaceId }),
  assemblyTree: (workspaceId: string) => generatePath('/w/:workspaceId/assembly-tree', { workspaceId }),
  standards: (workspaceId: string) => generatePath('/w/:workspaceId/standards', { workspaceId }),
}
