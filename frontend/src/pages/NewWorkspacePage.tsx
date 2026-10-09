import { CaretLeft, Check, TreeStructure } from '@phosphor-icons/react'
import { useId, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import type { DictionarySource, WorkspaceKind } from '../api/types'
import { getMe } from '../api/users'
import { createWorkspace, listWorkspaces } from '../api/workspaces'
import { ErrorNotice } from '../components/Notice'
import { PageHeader } from '../components/PageHeader'
import { useAsync } from '../hooks/useAsync'
import { useAccounts } from '../lib/accounts'
import { paths } from '../lib/paths'
import styles from './NewWorkspacePage.module.css'

/**
 * 와이어프레임 0 — 워크스페이스 만들기 (사이드바 없는 단독 화면, Apple ID 가입 화면처럼 가운데 한 줄)
 * 노션처럼 먼저 '혼자 / 팀과 함께'를 고르고(기본값 개인), 다음 단계에서 이름과 사전을 정한다.
 * 만든 사람(현재 사용자)은 백엔드가 소유자로 등록한다. 팀을 고르면 만든 뒤 바로 멤버 초대 화면으로 간다.
 */
export function NewWorkspacePage() {
  const navigate = useNavigate()
  const ids = { name: useId(), description: useId(), source: useId() }
  const { activeId } = useAccounts()
  // 전환 메뉴에서 고른 계정에 만든다 (그 계정이 소유자가 된다).
  const me = useAsync((signal) => getMe(signal), [activeId])
  const workspaces = useAsync((signal) => listWorkspaces(signal), [activeId])

  const [step, setStep] = useState<'kind' | 'details'>('kind')
  const [kind, setKind] = useState<WorkspaceKind>('personal')
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
        kind,
        dictionary_source: source,
        copy_from_workspace_id: source === 'copy' ? copyFromId : null,
      })
      navigate(kind === 'team' ? paths.members(workspace.id) : paths.workspaceHome(workspace.id))
    } catch (err) {
      setError(err)
      setSubmitting(false)
    }
  }

  if (step === 'kind') {
    return (
      <div className={styles.screen}>
        <span className={styles.appIcon} aria-hidden="true">
          <TreeStructure size={30} />
        </span>
        <PageHeader
          title="어떻게 쓸 건가요?"
          description="나중에 설정에서 바꿀 수 있어요. 혼자 쓰다가 팀원을 초대하면 팀 워크스페이스가 돼요."
        />
        {me.data && <p className={styles.account}>{me.data.email} 계정에 만들어요</p>}
        <form
          className="form"
          onSubmit={(event) => {
            event.preventDefault()
            setStep('details')
          }}
        >
          <fieldset className={styles.choices}>
            <legend className="visually-hidden">사용 방식</legend>
            <div className="group">
              <Choice
                name="kind"
                checked={kind === 'personal'}
                onChange={() => setKind('personal')}
                title="혼자 쓸게요"
                description="개인 워크스페이스. 내 작업과 사전을 혼자 관리해요"
              />
              <Choice
                name="kind"
                checked={kind === 'team'}
                onChange={() => setKind('team')}
                title="팀과 함께 쓸게요"
                description="팀 워크스페이스. 만든 뒤 바로 멤버를 초대해요"
              />
            </div>
          </fieldset>
          <div className={styles.actions}>
            <button type="submit" className="btn btn--primary btn--large">
              다음
            </button>
            <Link className="btn btn--plain" to="/">
              이미 있는 워크스페이스 열기
            </Link>
          </div>
        </form>
      </div>
    )
  }

  return (
    <div className={styles.screen}>
      <button type="button" className={`btn btn--plain ${styles.back}`} onClick={() => setStep('kind')}>
        <CaretLeft size={14} weight="bold" aria-hidden="true" />
        {kind === 'personal' ? '개인' : '팀'}
      </button>
      <span className={styles.appIcon} aria-hidden="true">
        <TreeStructure size={30} />
      </span>
      <PageHeader
        title={kind === 'personal' ? '개인 워크스페이스' : '팀 워크스페이스'}
        description="조선소나 공정마다 문자·기호 체계가 달라도 괜찮아요. 워크스페이스마다 따로 관리해요."
      />

      <form className="form" onSubmit={onSubmit}>
        <div className="group">
          <div className={styles.inlineField}>
            <label htmlFor={ids.name}>이름</label>
            <input
              id={ids.name}
              required
              maxLength={100}
              placeholder="예: 거제 2도크"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className={styles.inlineField}>
            <label htmlFor={ids.description}>설명</label>
            <input
              id={ids.description}
              placeholder="선택"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>
        </div>

        <fieldset className={styles.choices}>
          <legend className={styles.groupLabel}>문자·기호 사전</legend>
          <div className="group">
            <Choice
              name="dictionary_source"
              checked={source === 'empty'}
              onChange={() => setSource('empty')}
              title="빈 사전으로 시작"
              description="현장에서 쓰는 약어와 기호를 직접 등록해요"
            />
            <Choice
              name="dictionary_source"
              checked={source === 'copy'}
              onChange={() => setSource('copy')}
              disabled={copyCandidates.length === 0}
              title="다른 워크스페이스에서 복사"
              description="비슷한 공정의 사전을 가져와 고쳐 써요"
            />
          </div>
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
          <p className="field-hint">표준 용접 기준은 모든 워크스페이스가 함께 써요.</p>
          {workspaces.error !== undefined && <ErrorNotice error={workspaces.error} onRetry={workspaces.reload} />}
        </fieldset>

        {error !== undefined && <ErrorNotice error={error} />}

        <div className={styles.actions}>
          <button type="submit" className="btn btn--primary btn--large" disabled={submitting || !name.trim()}>
            {submitting ? '만드는 중' : '워크스페이스 만들기'}
          </button>
        </div>
      </form>
    </div>
  )
}

interface ChoiceProps {
  /** 같은 묶음의 라디오 이름 */
  name: string
  checked: boolean
  onChange: () => void
  disabled?: boolean
  title: string
  description: string
}

/** 설정 앱처럼 한 줄 전체를 누르는 선택지. 고른 줄 오른쪽에 체크 표시. */
function Choice({ name, checked, onChange, disabled, title, description }: ChoiceProps) {
  return (
    <label className={styles.choice} data-disabled={disabled || undefined}>
      <input
        type="radio"
        name={name}
        className="visually-hidden"
        checked={checked}
        disabled={disabled}
        onChange={onChange}
      />
      <span className={styles.choiceText}>
        <span>{title}</span>
        <span className={styles.choiceDesc}>{description}</span>
      </span>
      {checked && <Check className={styles.check} size={18} weight="bold" aria-hidden="true" />}
    </label>
  )
}
