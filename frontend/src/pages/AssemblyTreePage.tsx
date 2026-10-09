import type { AssemblyNode } from '../api/types'
import { getAssemblyTree } from '../api/workspaces'
import { AsyncView } from '../components/AsyncView'
import { PageHeader } from '../components/PageHeader'
import { useAsync } from '../hooks/useAsync'
import { useWorkspace } from '../hooks/useWorkspace'
import { ASSEMBLY_LEVEL_LABEL, ASSEMBLY_LEVELS } from '../lib/labels'

/** 와이어프레임 3b — 조립 트리 (워크스페이스별) */
export function AssemblyTreePage() {
  const workspace = useWorkspace()
  const tree = useAsync((signal) => getAssemblyTree(workspace.id, signal), [workspace.id])

  return (
    <div className="page">
      <PageHeader
        title="조립 트리"
        description="블록 → 대조립 → 중조립 → 소조립 → 부재 순서의 조립 경로입니다. 인식한 부재가 이 트리에 있는지로 DB 정합성을 검증합니다."
      />
      <AsyncView state={tree} isEmpty={(nodes) => nodes.length === 0} empty="등록된 조립 경로가 없습니다.">
        {(nodes) => (
          <ul className="tree" aria-label="조립 트리">
            {sortByPath(nodes).map((node) => (
              <li key={node.path} className="tree-node" data-depth={ASSEMBLY_LEVELS.indexOf(node.level)}>
                <span className="pill">{ASSEMBLY_LEVEL_LABEL[node.level]}</span>
                <strong>{node.node_id}</strong>
                <span className="mono field-hint">{node.path}</span>
              </li>
            ))}
          </ul>
        )}
      </AsyncView>
    </div>
  )
}

/** 경로를 '/' 단위로 비교해 부모 바로 아래에 자식이 오도록 정렬한다 (P-2 < P-10). */
function sortByPath(nodes: AssemblyNode[]): AssemblyNode[] {
  const collator = new Intl.Collator('ko', { numeric: true })
  return [...nodes].sort((a, b) => {
    const left = a.path.split('/')
    const right = b.path.split('/')
    for (let i = 0; i < Math.min(left.length, right.length); i++) {
      const order = collator.compare(left[i], right[i])
      if (order !== 0) return order
    }
    return left.length - right.length
  })
}
