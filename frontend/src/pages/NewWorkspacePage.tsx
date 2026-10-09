import { useId, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import type { DictionarySource } from '../api/types'
import { createWorkspace, listWorkspaces } from '../api/workspaces'
import { ErrorNotice } from '../components/Notice'
import { PageHeader } from '../components/PageHeader'
import { useAsync } from '../hooks/useAsync'
import { paths } from '../lib/paths'

/**
 * 와이어프레임 0 — 워크스페이스 만들기 (사이드바 없는 단독 화면)
 * TODO(인증): 로그인·멤버 기능이 생기면 만든 사람을 소유자로 등록한다.
 */
export function NewWorkspacePage() {
  const navigate = useNavigate()
  const ids = { name: useId(), description: useId(), source: useId() }
  const workspaces = useAsync((signal) => listWorkspaces(signal), [])

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [source, setSource] = useState<DictionarySource>('empty')
  const [copyFrom, setCopyFrom] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<unknown>()

  const copyCandidates = workspaces.data ?? []
  const copyFromId = copyFrom || copyCandidates[0]?.id || ''

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError(undefined)
    try {
      const workspace = await createWorkspace({
        name: name.trim(),
        description: description.trim() || null,
        dictionary_source: source,
        copy_from_workspace_id: source === 'copy' ? copyFromId : null,
      })
      navigate(paths.workspaceHome(workspace.id))
    } catch (err) {
      setError(err)
      setSubmitting(false)
    }
  }

  return (
    <div className="page page--narrow">
      <PageHeader
        eyebrow={<Link to="/">← 돌아가기</Link>}
        title="워크스페이스 만들기"
        description="조선소·공정 단위로 워크스페이스를 만듭니다. 작업·문자/기호 사전·조립 트리는 워크스페이스마다 따로 관리하고, 표준 용접 기준은 모든 워크스페이스가 함께 씁니다."
      />

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
            placeholder="예: 거제 조선소 · 2도크"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor={ids.description} className="field-label">
            설명 (선택)
          </label>
          <textarea
            id={ids.description}
            className="input"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>

        <fieldset className="field">
          <legend className="field-label">문자/기호 사전</legend>
          <label className="choice">
            <input
              type="radio"
              name="dictionary_source"
              value="empty"
              checked={source === 'empty'}
              onChange={() => setSource('empty')}
            />
            빈 사전으로 시작
          </label>
          <label className="choice">
            <input
              type="radio"
              name="dictionary_source"
              value="copy"
              checked={source === 'copy'}
              onChange={() => setSource('copy')}
              disabled={copyCandidates.length === 0}
            />
            기존 워크스페이스의 사전 복사
          </label>
          {source === 'copy' && (
            <>
              <label htmlFor={ids.source} className="visually-hidden">
                복사할 워크스페이스
              </label>
              <select
                id={ids.source}
                className="input"
                value={copyFromId}
                onChange={(event) => setCopyFrom(event.target.value)}
              >
                {copyCandidates.map((workspace) => (
                  <option key={workspace.id} value={workspace.id}>
                    {workspace.name}
                  </option>
                ))}
              </select>
            </>
          )}
          {workspaces.error !== undefined && <ErrorNotice error={workspaces.error} onRetry={workspaces.reload} />}
        </fieldset>

        {error !== undefined && <ErrorNotice error={error} />}

        <p className="button-row">
          <button type="submit" className="btn btn--primary" disabled={submitting || !name.trim()}>
            {submitting ? '만드는 중…' : '만들기'}
          </button>
        </p>
      </form>
    </div>
  )
}
