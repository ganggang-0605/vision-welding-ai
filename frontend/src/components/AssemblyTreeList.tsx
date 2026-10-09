import { CaretDown, Square } from '@phosphor-icons/react'
import type { CSSProperties } from 'react'
import type { AssemblyNode } from '../api/types'
import { ASSEMBLY_LEVEL_LABEL, ASSEMBLY_LEVELS } from '../lib/labels'
import styles from './AssemblyTreeList.module.css'

interface AssemblyTreeListProps {
  nodes: AssemblyNode[]
  /** 목록 이름 (스크린 리더용) */
  label?: string
}

/** 조립 트리 한 블록을 파인더 목록처럼 단계별 들여쓰기로 (블록 → 대조립 → 중조립 → 소조립 → 부재) */
export function AssemblyTreeList({ nodes, label = '조립 트리' }: AssemblyTreeListProps) {
  return (
    <ul className={styles.tree} aria-label={label}>
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
