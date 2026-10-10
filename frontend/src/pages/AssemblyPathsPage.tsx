import { getWorkspaceAssemblyTree } from '../api/workspaces'
import { AssemblyTreeList } from '../components/AssemblyTreeList'
import { AsyncView } from '../components/AsyncView'
import { PageHeader } from '../components/PageHeader'
import { useAsync } from '../hooks/useAsync'
import { useWorkspace } from '../hooks/useWorkspace'

/** 워크스페이스 사전 > 조립 경로 사전 — 워크스페이스에 하나인 조립 트리 (블록 → 대조립 → 중조립 → 소조립 → 부재) */
export function AssemblyPathsPage() {
  const workspace = useWorkspace()
  const tree = useAsync((signal) => getWorkspaceAssemblyTree(workspace.id, signal), [workspace.id])

  return (
    <div className="page">
      <PageHeader
        title="조립 경로 사전"
        description="블록에서 부재까지 조립 순서예요. 인식한 부재가 여기 있는지로 해석을 검증해요."
      />
      <AsyncView state={tree} isEmpty={(nodes) => nodes.length === 0} empty="아직 조립 경로가 없어요.">
        {(nodes) => (
          <section className="section">
            <p className="section-desc">
              노드 {nodes.length}개 · 부재 {nodes.filter((node) => node.level === 'PART').length}개
            </p>
            <AssemblyTreeList nodes={nodes} label={`${workspace.name} 조립 트리`} />
          </section>
        )}
      </AsyncView>
    </div>
  )
}
