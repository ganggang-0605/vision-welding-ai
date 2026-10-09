import { Link, Outlet } from 'react-router'
import { PageHeader } from '../components/PageHeader'
import type { ProjectOutletContext } from '../hooks/useProject'
import { useRequiredParam } from '../hooks/useRequiredParam'
import { useWorkspaceContext } from '../hooks/useWorkspace'
import { paths } from '../lib/paths'

/**
 * 프로젝트(호선) 화면 공통: 주소의 :projectId 를 워크스페이스의 프로젝트 목록에서 찾아 하위 페이지에 넘긴다.
 * 목록은 WorkspaceLayout 이 이미 불러왔으므로 따로 요청하지 않는다. 페이지에서는 useProject().
 */
export function ProjectLayout() {
  const context = useWorkspaceContext()
  const projectId = useRequiredParam('projectId')
  const project = context.projects.find((item) => item.id === projectId)

  if (!project) {
    return (
      <div className="page">
        <PageHeader
          breadcrumb={[{ label: '홈', to: paths.workspaceHome(context.workspace.id) }, { label: projectId }]}
          title="프로젝트를 찾을 수 없어요"
          description={`'${projectId}' 프로젝트가 이 워크스페이스에 없어요.`}
        />
        <Link className="btn btn--primary" to={paths.workspaceHome(context.workspace.id)}>
          홈으로
        </Link>
      </div>
    )
  }

  return <Outlet context={{ ...context, project } satisfies ProjectOutletContext} />
}
