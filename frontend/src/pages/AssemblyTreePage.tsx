import { CaretDown, Square } from '@phosphor-icons/react'
import type { CSSProperties } from 'react'
import type { AssemblyNode } from '../api/types'
import { getAssemblyTree } from '../api/projects'
import { AsyncView } from '../components/AsyncView'
import { PageHeader } from '../components/PageHeader'
import { useAsync } from '../hooks/useAsync'
import { useProject } from '../hooks/useProject'
import { useWorkspace } from '../hooks/useWorkspace'
import { paths } from '../lib/paths'
import { ASSEMBLY_LEVEL_LABEL, ASSEMBLY_LEVELS } from '../lib/labels'
import styles from './AssemblyTreePage.module.css'

/** 와이어프레임 3b — 조립 트리 (프로젝트(블록)별, 파인더 목록처럼 단계별 들여쓰기) */
export function AssemblyTreePage() {
  const workspace = useWorkspace()
  const project = useProject()
  const tree = useAsync((signal) => getAssemblyTree(workspace.id, project.id, signal), [workspace.id, project.id])

  return (
    <div className="page">
      <PageHeader
        breadcrumb={[{ label: project.name, to: paths.project(workspace.id, project.id) }, { label: '조립 트리' }]}
        title="조립 트리"
        description="블록에서 부재까지 조립 순서예요. 인식한 부재가 여기 있는지로 해석을 검증해요."
      />
      <AsyncView state={tree} isEmpty={(nodes) => nodes.length === 0} empty="이 블록에는 아직 조립 경로가 없어요. 도면에서 가져오는 기능은 준비 중이에요.">
        {(nodes) => (
          <ul className={styles.tree} aria-label="조립 트리">
            {sortByPath(nodes).map((node) => {
              const isPart = node.level === 'PART'
              return (
                <li
                  key={node.path}
                  className={styles.node}
                  style={{ '--depth': ASSEMBLY_LEVELS.indexOf(node.level) } as CSSProperties}
                  title={node.path}
                >
                  {isPart ? (
                    <Square className={styles.icon} size={13} aria-hidden="true" />
                  ) : (
                    <CaretDown className={styles.icon} size={13} weight="bold" aria-hidden="true" />
                  )}
                  <span className={styles.id}>{node.node_id}</span>
                  <span className={styles.level}>{ASSEMBLY_LEVEL_LABEL[node.level]}</span>
                </li>
              )
            })}
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
