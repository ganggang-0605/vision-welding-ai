import { Link } from 'react-router'
import { getAssemblyTree } from '../api/projects'
import type { AssemblyNode, Project } from '../api/types'
import { AssemblyTreeList } from '../components/AssemblyTreeList'
import { AsyncView } from '../components/AsyncView'
import { PageHeader } from '../components/PageHeader'
import { useAsync } from '../hooks/useAsync'
import { useWorkspaceContext } from '../hooks/useWorkspace'
import { paths } from '../lib/paths'

interface BlockTree {
  project: Project
  nodes: AssemblyNode[]
}

/** 워크스페이스 사전 > 조립 경로 사전 — 이 워크스페이스의 모든 블록 조립 트리를 한곳에서 (블록별 화면은 AssemblyTreePage) */
export function AssemblyPathsPage() {
  const { workspace, projects } = useWorkspaceContext()
  const trees = useAsync(
    (signal) =>
      Promise.all(
        projects.map(async (project): Promise<BlockTree> => ({
          project,
          nodes: await getAssemblyTree(workspace.id, project.id, signal),
        })),
      ),
    [workspace.id, projects],
  )

  return (
    <div className="page">
      <PageHeader
        title="조립 경로 사전"
        description="이 워크스페이스의 블록마다 블록에서 부재까지 조립 순서예요. 인식한 부재가 여기 있는지로 해석을 검증해요."
      />
      <AsyncView
        state={trees}
        isEmpty={(list) => list.length === 0}
        empty={
          <>
            아직 블록이 없어요. <Link to={paths.newProject(workspace.id)}>블록을 추가</Link>하면 조립 경로를 볼 수 있어요.
          </>
        }
      >
        {(list) =>
          list.map(({ project, nodes }) => {
            const titleId = `assembly-${project.id}`
            const parts = nodes.filter((node) => node.level === 'PART').length
            return (
              <section key={project.id} className="section" aria-labelledby={titleId}>
                <div className="section-head">
                  <h2 id={titleId} className="section-title">
                    {project.name}
                  </h2>
                  <Link className="btn btn--small" to={paths.assemblyTree(workspace.id, project.id)}>
                    블록에서 보기
                  </Link>
                </div>
                {nodes.length === 0 ? (
                  <p className="state">아직 조립 경로가 없어요.</p>
                ) : (
                  <>
                    <p className="section-desc">
                      노드 {nodes.length}개 · 부재 {parts}개
                    </p>
                    <AssemblyTreeList nodes={nodes} label={`${project.name} 조립 트리`} />
                  </>
                )}
              </section>
            )
          })
        }
      </AsyncView>
    </div>
  )
}
