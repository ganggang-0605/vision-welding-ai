import { useId, useState, type FormEvent } from 'react'
import type { AssemblyLevel, AssemblyNode } from '../api/types'
import { addAssemblyNode, deleteAssemblyNode, getWorkspaceAssemblyTree } from '../api/workspaces'
import { AssemblyTreeList } from '../components/AssemblyTreeList'
import { AsyncView } from '../components/AsyncView'
import { ErrorNotice } from '../components/Notice'
import { PageHeader } from '../components/PageHeader'
import { useAsync } from '../hooks/useAsync'
import { useWorkspace } from '../hooks/useWorkspace'
import { ASSEMBLY_LEVEL_LABEL, ASSEMBLY_LEVELS } from '../lib/labels'

/** 워크스페이스 사전 > 조립 경로 사전 — 워크스페이스에 하나인 조립 트리 (블록 → 대조립 → 중조립 → 소조립 → 부재) */
export function AssemblyPathsPage() {
  const workspace = useWorkspace()
  const tree = useAsync((signal) => getWorkspaceAssemblyTree(workspace.id, signal), [workspace.id])
  const [actionError, setActionError] = useState<unknown>()

  const onDelete = async (node: AssemblyNode) => {
    if (!window.confirm(`'${node.path}' 경로를 지울까요?`)) return
    setActionError(undefined)
    try {
      await deleteAssemblyNode(workspace.id, node.path)
      tree.reload()
    } catch (err) {
      setActionError(err)
    }
  }

  return (
    <div className="page">
      <PageHeader
        title="조립 경로 사전"
        description="블록에서 부재까지 조립 순서예요. 인식한 부재가 여기 있는지로 해석을 검증해요."
      />

      {actionError !== undefined && <ErrorNotice error={actionError} />}

      <AsyncView
        state={tree}
        keepPreviousData
        isEmpty={(nodes) => nodes.length === 0}
        empty="아직 조립 경로가 없어요. 아래에서 블록부터 추가해 보세요."
      >
        {(nodes) => (
          <section className="section">
            <p className="section-desc">
              노드 {nodes.length}개 · 부재 {nodes.filter((node) => node.level === 'PART').length}개
            </p>
            <AssemblyTreeList nodes={nodes} label={`${workspace.name} 조립 트리`} onDelete={onDelete} />
          </section>
        )}
      </AsyncView>

      <AddNodeForm workspaceId={workspace.id} nodes={tree.data ?? []} onAdded={tree.reload} />
    </div>
  )
}

const ROOT = ''

function AddNodeForm({
  workspaceId,
  nodes,
  onAdded,
}: {
  workspaceId: string
  nodes: AssemblyNode[]
  onAdded: () => void
}) {
  const ids = { parent: useId(), nodeId: useId(), level: useId() }
  const [parentPath, setParentPath] = useState(ROOT)
  const [nodeId, setNodeId] = useState('')
  const [level, setLevel] = useState<AssemblyLevel | ''>('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<unknown>()

  const parents = nodes.filter((node) => node.level !== 'PART').sort((a, b) => a.path.localeCompare(b.path))
  const parent = parents.find((node) => node.path === parentPath)
  // 고를 수 있는 단계: 상위 노드보다 아래 (최상위면 전부). 비우면 바로 아래 단계
  const levels = ASSEMBLY_LEVELS.slice(parent ? ASSEMBLY_LEVELS.indexOf(parent.level) + 1 : 0)

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError(undefined)
    try {
      await addAssemblyNode(workspaceId, {
        node_id: nodeId.trim(),
        parent_path: parentPath || null,
        level: level || null,
      })
      setNodeId('')
      onAdded()
    } catch (err) {
      setError(err)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="section">
      <h2 className="section-title">새 경로</h2>
      <form className="form" onSubmit={onSubmit}>
        <div className="grid-2">
          <div className="field">
            <label htmlFor={ids.parent} className="field-label">
              상위 노드
            </label>
            <select
              id={ids.parent}
              className="input mono"
              value={parentPath}
              onChange={(event) => {
                setParentPath(event.target.value)
                setLevel('')
              }}
            >
              <option value={ROOT}>없음 (최상위 블록)</option>
              {parents.map((node) => (
                <option key={node.path} value={node.path}>
                  {node.path}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor={ids.nodeId} className="field-label">
              노드 ID
            </label>
            <input
              id={ids.nodeId}
              className="input mono"
              required
              pattern="[^\/]+"
              title="'/' 없이 적어 주세요"
              placeholder={parent ? '예: P-1' : '예: A1'}
              value={nodeId}
              onChange={(event) => setNodeId(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor={ids.level} className="field-label">
              단계
            </label>
            <select
              id={ids.level}
              className="input"
              value={level}
              onChange={(event) => setLevel(event.target.value as AssemblyLevel | '')}
            >
              <option value="">
                {ASSEMBLY_LEVEL_LABEL[levels[0]]} ({parent ? '바로 아래 단계' : '기본'})
              </option>
              {levels.slice(1).map((value) => (
                <option key={value} value={value}>
                  {ASSEMBLY_LEVEL_LABEL[value]}
                </option>
              ))}
            </select>
          </div>
        </div>
        {error !== undefined && <ErrorNotice error={error} />}
        <p className="button-row">
          <button type="submit" className="btn btn--primary" disabled={submitting}>
            {submitting ? '추가하는 중' : '추가'}
          </button>
        </p>
      </form>
    </section>
  )
}
