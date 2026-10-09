/**
 * 라우트 정의 (React Router 데이터 라우터).
 * 워크스페이스 → 프로젝트(블록) → 작업 순서로 주소가 깊어진다. 화면 ↔ 와이어프레임 대응은 frontend/README.md 의 '라우트' 표 참고.
 */
import { createBrowserRouter, redirect } from 'react-router'
import { ProjectLayout } from './layouts/ProjectLayout'
import { SettingsLayout } from './layouts/SettingsLayout'
import { WorkspaceLayout } from './layouts/WorkspaceLayout'
import { getActiveAccountId } from './lib/accounts'
import { DEFAULT_WORKSPACE_ID, paths, readLastWorkspaceId } from './lib/paths'
import { AssemblyTreePage } from './pages/AssemblyTreePage'
import { JobProcessPage } from './pages/JobProcessPage'
import { JobResultPage } from './pages/JobResultPage'
import { JobReviewPage } from './pages/JobReviewPage'
import { JobSummaryPage } from './pages/JobSummaryPage'
import { LoginPage } from './pages/LoginPage'
import { NewJobPage } from './pages/NewJobPage'
import { NewProjectPage } from './pages/NewProjectPage'
import { NewWorkspacePage } from './pages/NewWorkspacePage'
import { NotFoundPage } from './pages/NotFoundPage'
import { PreferencesPage } from './pages/PreferencesPage'
import { ProjectPage } from './pages/ProjectPage'
import { RouteErrorPage } from './pages/RouteErrorPage'
import { SymbolsPage } from './pages/SymbolsPage'
import { WeldingStandardsPage } from './pages/WeldingStandardsPage'
import { WorkspaceHomePage } from './pages/WorkspaceHomePage'
import { WorkspaceGeneralPage } from './pages/WorkspaceGeneralPage'
import { WorkspaceMembersPage } from './pages/WorkspaceMembersPage'

export const router = createBrowserRouter([
  {
    ErrorBoundary: RouteErrorPage,
    children: [
      {
        path: '/',
        // 노션처럼 지금 계정이 마지막으로 연 워크스페이스로 바로 들어간다. 로그인한 계정이 없으면 계정 고르기.
        loader: () => {
          const accountId = getActiveAccountId()
          if (!accountId) return redirect(paths.login())
          return redirect(paths.workspaceHome(readLastWorkspaceId(accountId) ?? DEFAULT_WORKSPACE_ID))
        },
      },
      { path: '/login', Component: LoginPage },
      { path: '/workspaces/new', Component: NewWorkspacePage },
      {
        path: '/w/:workspaceId',
        Component: WorkspaceLayout,
        children: [
          { index: true, Component: WorkspaceHomePage },
          {
            // 노션의 설정 창처럼 왼쪽에 '내 설정 / 워크스페이스' 묶음
            path: 'settings',
            Component: SettingsLayout,
            children: [
              { index: true, Component: WorkspaceGeneralPage },
              { path: 'members', Component: WorkspaceMembersPage },
              { path: 'preferences', Component: PreferencesPage },
            ],
          },
          { path: 'symbols', Component: SymbolsPage },
          { path: 'standards', Component: WeldingStandardsPage },
          { path: 'projects/new', Component: NewProjectPage },
          {
            path: 'p/:projectId',
            Component: ProjectLayout,
            children: [
              { index: true, Component: ProjectPage },
              { path: 'assembly-tree', Component: AssemblyTreePage },
              { path: 'jobs/new', Component: NewJobPage },
              { path: 'jobs/:jobId', Component: JobResultPage },
              { path: 'jobs/:jobId/review', Component: JobReviewPage },
              { path: 'jobs/:jobId/process/:stage?', Component: JobProcessPage },
              { path: 'jobs/:jobId/summary', Component: JobSummaryPage },
            ],
          },
          // 워크스페이스 안의 없는 주소는 사이드바를 유지한 채 404
          { path: '*', Component: NotFoundPage },
        ],
      },
      { path: '*', Component: NotFoundPage },
    ],
  },
])
