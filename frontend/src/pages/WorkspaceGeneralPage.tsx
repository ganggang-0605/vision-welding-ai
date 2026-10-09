import { useId, useState, type FormEvent } from 'react'
import { isApiError } from '../api/client'
import type { Workspace, WorkspaceKind } from '../api/types'
import { updateWorkspace } from '../api/workspaces'
import { ErrorNotice, Notice } from '../components/Notice'
import { PageHeader } from '../components/PageHeader'
import { useWorkspaceContext } from '../hooks/useWorkspace'

/**
 * 설정 > 워크스페이스 > 일반: 이름·설명, 사용 방식(개인/팀). 지금 워크스페이스에만 적용된다.
 * TODO(인증): 지금은 누구나 바꿀 수 있다. 로그인이 생기면 소유자만 바꿀 수 있게 한다.
 */
export function WorkspaceGeneralPage() {
  const { workspace, reloadWorkspace } = useWorkspaceContext()
  return (
    <>
      <PageHeader title="일반" documentTitle={`${workspace.name} 설정`} description="이 워크스페이스에만 적용돼요." />
      <GeneralSection key={workspace.id} workspace={workspace} onSaved={reloadWorkspace} />
      <KindSection workspace={workspace} onChanged={reloadWorkspace} />
    </>
  )
}

function GeneralSection({ workspace, onSaved }: { workspace: Workspace; onSaved: () => void }) {
  const ids = { name: useId(), description: useId() }
  const [name, setName] = useState(workspace.name)
  const [description, setDescription] = useState(workspace.description ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<unknown>()
  const [saved, setSaved] = useState(false)
  const changed = name.trim() !== workspace.name || (description.trim() || null) !== workspace.description

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSaving(true)
    setError(undefined)
    setSaved(false)
    try {
      await updateWorkspace(workspace.id, { name: name.trim(), description: description.trim() || null })
      setSaved(true)
      onSaved()
    } catch (err) {
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section aria-labelledby="general-title">
      <h2 id="general-title" className="section-title">
        이름과 설명
      </h2>
      <form className="form" onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor={ids.name} className="field-label">
            이름
          </label>
          <input
            id={ids.name}
            className="input"
            required
            maxLength={100}
            value={name}
            onChange={(event) => {
              setName(event.target.value)
              setSaved(false)
            }}
          />
        </div>
        <div className="field">
          <label htmlFor={ids.description} className="field-label">
            설명
          </label>
          <input
            id={ids.description}
            className="input"
            placeholder="선택"
            value={description}
            onChange={(event) => {
              setDescription(event.target.value)
              setSaved(false)
            }}
          />
        </div>
        {error !== undefined && <ErrorNotice error={error} />}
        <p className="button-row">
          <button type="submit" className="btn btn--primary" disabled={saving || !changed || !name.trim()}>
            {saving ? '저장하는 중' : '저장'}
          </button>
          {saved && !changed && <span className="secondary">저장했어요</span>}
        </p>
      </form>
    </section>
  )
}

const KIND_OPTIONS: { value: WorkspaceKind; label: string; description: string }[] = [
  { value: 'personal', label: '개인', description: '혼자 쓰는 워크스페이스예요.' },
  { value: 'team', label: '팀', description: '멤버와 함께 써요. 블록과 사전을 같이 보고 고쳐요.' },
]

function KindSection({ workspace, onChanged }: { workspace: Workspace; onChanged: () => void }) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<unknown>()
  // 멤버가 있는 팀은 개인으로 되돌릴 수 없다 (백엔드도 409).
  const locked = workspace.kind === 'team' && workspace.member_count > 1

  const change = async (kind: WorkspaceKind) => {
    if (kind === workspace.kind) return
    setSaving(true)
    setError(undefined)
    try {
      await updateWorkspace(workspace.id, { kind })
      onChanged()
    } catch (err) {
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  const current = KIND_OPTIONS.find((option) => option.value === workspace.kind)

  return (
    <section className="section" aria-labelledby="kind-title">
      <h2 id="kind-title" className="section-title">
        사용 방식
      </h2>
      <div className="segmented" role="group" aria-label="사용 방식">
        {KIND_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            aria-pressed={workspace.kind === option.value}
            disabled={saving || (option.value === 'personal' && locked)}
            onClick={() => change(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
      <p className="field-hint">
        {current?.description}
        {locked && ' 멤버가 있어서 개인으로 되돌릴 수 없어요.'}
      </p>
      {error !== undefined &&
        (isApiError(error, 409) ? (
          <Notice tone="warning">멤버가 있어서 개인으로 되돌릴 수 없어요.</Notice>
        ) : (
          <ErrorNotice error={error} />
        ))}
    </section>
  )
}
