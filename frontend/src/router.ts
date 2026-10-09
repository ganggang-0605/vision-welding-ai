/**
 * 라우트 정의 (React Router 데이터 라우터).
 * 화면 ↔ 와이어프레임 대응은 frontend/README.md 의 '라우트' 표 참고.
 */
import { createBrowserRouter, redirect } from 'react-router'
import { WorkspaceLayout } from './layouts/WorkspaceLayout'
import { DEFAULT_WORKSPACE_ID, paths } from './lib/paths'
import { AssemblyTreePage } from './pages/AssemblyTreePage'
import { JobResultPage } from './pages/JobResultPage'
import { JobReviewPage } from './pages/JobReviewPage'
import { JobSummaryPage } from './pages/JobSummaryPage'
import { NewJobPage } from './pages/NewJobPage'
import { NewWorkspacePage } from './pages/NewWorkspacePage'
import { NotFoundPage } from './pages/NotFoundPage'
import { RouteErrorPage } from './pages/RouteErrorPage'
import { SymbolsPage } from './pages/SymbolsPage'
import { WeldingStandardsPage } from './pages/WeldingStandardsPage'
import { WorkspaceHomePage } from './pages/WorkspaceHomePage'

export const router = createBrowserRouter([
  {
    ErrorBoundary: RouteErrorPage,
    children: [
      {
        path: '/',
        // TODO: 마지막으로 연 워크스페이스로 보내기 (지금은 데모 워크스페이스 고정)
        loader: () => redirect(paths.workspaceHome(DEFAULT_WORKSPACE_ID)),
      },
      { path: '/workspaces/new', Component: NewWorkspacePage },
      {
        path: '/w/:workspaceId',
        Component: WorkspaceLayout,
        children: [
          { index: true, Component: WorkspaceHomePage },
          { path: 'jobs/new', Component: NewJobPage },
          { path: 'jobs/:jobId', Component: JobResultPage },
          { path: 'jobs/:jobId/review', Component: JobReviewPage },
          { path: 'jobs/:jobId/summary', Component: JobSummaryPage },
          { path: 'symbols', Component: SymbolsPage },
          { path: 'assembly-tree', Component: AssemblyTreePage },
          { path: 'standards', Component: WeldingStandardsPage },
          // 워크스페이스 안의 없는 주소는 사이드바를 유지한 채 404
          { path: '*', Component: NotFoundPage },
        ],
      },
      { path: '*', Component: NotFoundPage },
    ],
  },
])
