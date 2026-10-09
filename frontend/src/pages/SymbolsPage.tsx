import { Trash } from '@phosphor-icons/react'
import { useId, useState, type FormEvent } from 'react'
import type { SymbolEntry, SymbolKind } from '../api/types'
import { createSymbol, deleteSymbol, listSymbols } from '../api/workspaces'
import { AsyncView } from '../components/AsyncView'
import { ErrorNotice } from '../components/Notice'
import { PageHeader } from '../components/PageHeader'
import { useAsync } from '../hooks/useAsync'
import { useWorkspace } from '../hooks/useWorkspace'
import { jointTypeLabel, SYMBOL_KIND_LABEL } from '../lib/labels'

/** 와이어프레임 3a — 문자·기호 사전 (워크스페이스별) */
export function SymbolsPage() {
  const workspace = useWorkspace()
  const symbols = useAsync((signal) => listSymbols(workspace.id, signal), [workspace.id])
  const [actionError, setActionError] = useState<unknown>()

  const onDelete = async (entry: SymbolEntry) => {
    if (!window.confirm(`'${entry.code}' 항목을 지울까요?`)) return
    setActionError(undefined)
    try {
      await deleteSymbol(workspace.id, entry.id)
      symbols.reload()
    } catch (err) {
      setActionError(err)
    }
  }

  return (
    <div className="page">
      <PageHeader
        title="문자·기호 사전"
        description="해석할 때 이 사전과 대조해요. 이 워크스페이스에서만 쓰여요."
      />

      {actionError !== undefined && <ErrorNotice error={actionError} />}

      <AsyncView
        state={symbols}
        keepPreviousData
        isEmpty={(list) => list.length === 0}
        empty="아직 등록한 표기가 없어요. 아래에서 현장에서 쓰는 약어나 기호를 추가해 보세요."
      >
        {(list) => (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">표기</th>
                  <th scope="col">종류</th>
                  <th scope="col">뜻</th>
                  <th scope="col">비슷한 표기</th>
                  <th scope="col">이음 형태</th>
                  <th scope="col">
                    <span className="visually-hidden">지우기</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {list.map((entry) => (
                  <tr key={entry.id}>
                    <td className="code">{entry.code}</td>
                    <td className="secondary">{SYMBOL_KIND_LABEL[entry.kind]}</td>
                    <td className="cell-title">{entry.meaning}</td>
                    <td className="secondary">{entry.aliases.join(', ')}</td>
                    <td className="secondary">{entry.welding_joint_type && jointTypeLabel(entry.welding_joint_type)}</td>
                    <td className="cell-action">
                      {/* TODO: 수정(updateSymbol) UI */}
                      <button
                        type="button"
                        className="icon-btn icon-btn--danger"
                        onClick={() => onDelete(entry)}
                        title="지우기"
                      >
                        <Trash size={16} aria-hidden="true" />
                        <span className="visually-hidden">{entry.code} 지우기</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </AsyncView>

      <AddSymbolForm workspaceId={workspace.id} onAdded={symbols.reload} />
    </div>
  )
}

function AddSymbolForm({ workspaceId, onAdded }: { workspaceId: string; onAdded: () => void }) {
  const ids = { code: useId(), kind: useId(), meaning: useId(), aliases: useId(), joint: useId() }
  const [code, setCode] = useState('')
  const [kind, setKind] = useState<SymbolKind>('text')
  const [meaning, setMeaning] = useState('')
  const [aliases, setAliases] = useState('')
  const [jointType, setJointType] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<unknown>()

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError(undefined)
    try {
      await createSymbol(workspaceId, {
        code: code.trim(),
        kind,
        meaning: meaning.trim(),
        aliases: aliases
          .split(',')
          .map((alias) => alias.trim())
          .filter(Boolean),
        welding_joint_type: jointType.trim() || null,
      })
      setCode('')
      setMeaning('')
      setAliases('')
      setJointType('')
      onAdded()
    } catch (err) {
      setError(err)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="section">
      <h2 className="section-title">새 표기</h2>
      <form className="form" onSubmit={onSubmit}>
        <div className="grid-2">
          <div className="field">
            <label htmlFor={ids.code} className="field-label">
              표기
            </label>
            <input
              id={ids.code}
              className="input mono"
              required
              placeholder="예: FW"
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor={ids.kind} className="field-label">
              종류
            </label>
            <select
              id={ids.kind}
              className="input"
              value={kind}
              onChange={(event) => setKind(event.target.value as SymbolKind)}
            >
              <option value="text">{SYMBOL_KIND_LABEL.text}</option>
              <option value="symbol">{SYMBOL_KIND_LABEL.symbol}</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor={ids.meaning} className="field-label">
              뜻
            </label>
            <input
              id={ids.meaning}
              className="input"
              required
              placeholder="예: 필렛 용접"
              value={meaning}
              onChange={(event) => setMeaning(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor={ids.aliases} className="field-label">
              비슷한 표기 (쉼표로 구분)
            </label>
            <input
              id={ids.aliases}
              className="input"
              placeholder="예: F/W"
              value={aliases}
              onChange={(event) => setAliases(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor={ids.joint} className="field-label">
              이음 형태 (선택)
            </label>
            <input
              id={ids.joint}
              className="input"
              placeholder="예: FILLET"
              value={jointType}
              onChange={(event) => setJointType(event.target.value)}
            />
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
