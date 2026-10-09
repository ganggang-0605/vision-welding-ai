import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { useLocation } from 'react-router'
import { isApiError } from '../api/client'
import type { Workspace, WorkspaceKind } from '../api/types'
import { inviteMember, listMembers, updateWorkspace } from '../api/workspaces'
import { AsyncView } from '../components/AsyncView'
import { ErrorNotice, Notice } from '../components/Notice'
import { PageHeader } from '../components/PageHeader'
import { useAsync } from '../hooks/useAsync'
import { useWorkspaceContext } from '../hooks/useWorkspace'
import { MEMBER_ROLE_LABEL } from '../lib/labels'
import { THEME_OPTIONS, useThemePreference } from '../lib/theme'
import styles from './WorkspaceSettingsPage.module.css'

/**
 * 워크스페이스 설정과 멤버 (노션의 Settings & members).
 * 개인 워크스페이스에 팀원을 초대하면 백엔드가 팀 워크스페이스로 바꾼다.
 * TODO(인증): 지금은 누구나 초대·수정할 수 있다. 로그인이 생기면 소유자만 바꿀 수 있게 한다.
 */
export function WorkspaceSettingsPage() {
  const { workspace, reloadWorkspace } = useWorkspaceContext()
  const members = useAsync((signal) => listMembers(workspace.id, signal), [workspace.id])
  const membersRef = useRef<HTMLElement>(null)
  const { hash } = useLocation()

  // 사이드바·전환 메뉴의 '팀원 초대'(#members)로 들어오면 멤버 칸으로 내려간다.
  useEffect(() => {
    if (hash === '#members') membersRef.current?.scrollIntoView({ block: 'start' })
  }, [hash])

  const onChanged = () => {
    reloadWorkspace()
    members.reload()
  }

  return (
    <div className="page page--narrow">
      <PageHeader title="설정과 멤버" description={workspace.name} />

      <GeneralSection key={workspace.id} workspace={workspace} onSaved={reloadWorkspace} />
      <KindSection workspace={workspace} onChanged={onChanged} />
      <AppearanceSection />

      <section ref={membersRef} id="members" className={`section ${styles.anchor}`} aria-labelledby="members-title">
        <h2 id="members-title" className="section-title">
          멤버
        </h2>
        <AsyncView state={members} keepPreviousData>
          {(list) => (
            <ul className="group">
              {list.map((member) => (
                <li key={member.user_id} className={styles.member}>
                  <span className={styles.avatar} aria-hidden="true">
                    {member.name.charAt(0)}
                  </span>
                  <span className={styles.memberText}>
                    <span>{member.name}</span>
                    <span className={styles.email}>{member.email}</span>
                  </span>
                  <span className="status">{MEMBER_ROLE_LABEL[member.role]}</span>
                </li>
              ))}
            </ul>
          )}
        </AsyncView>
        <InviteForm workspace={workspace} onInvited={onChanged} />
      </section>
    </div>
  )
}

/** 화면 모드. 워크스페이스가 아니라 이 브라우저에 저장되는 내 설정이다. */
function AppearanceSection() {
  const [preference, setPreference] = useThemePreference()
  return (
    <section className="section" aria-labelledby="appearance-title">
      <h2 id="appearance-title" className="section-title">
        화면 모드
      </h2>
      <div className="segmented" role="group" aria-label="화면 모드">
        {THEME_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            aria-pressed={preference === option.value}
            onClick={() => setPreference(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
      <p className="field-hint">
        {preference === 'system' ? '맥·휴대폰의 라이트/다크 설정을 따라가요. ' : ''}이 브라우저에만 적용돼요.
      </p>
    </section>
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
    <section className="section" aria-labelledby="general-title">
      <h2 id="general-title" className="section-title">
        일반
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

function InviteForm({ workspace, onInvited }: { workspace: Workspace; onInvited: () => void }) {
  const ids = { name: useId(), email: useId() }
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<unknown>()
  const [invited, setInvited] = useState<{ name: string; becameTeam: boolean }>()

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError(undefined)
    setInvited(undefined)
    try {
      const member = await inviteMember(workspace.id, { name: name.trim(), email: email.trim() })
      setInvited({ name: member.name, becameTeam: workspace.kind === 'personal' })
      setName('')
      setEmail('')
      onInvited()
    } catch (err) {
      setError(err)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className={styles.invite} onSubmit={onSubmit}>
      <h3 className={styles.inviteTitle}>{workspace.kind === 'personal' ? '팀원을 초대해 함께 쓰기' : '멤버 초대'}</h3>
      {workspace.kind === 'personal' && (
        <p className="field-hint">초대하면 이 워크스페이스가 팀 워크스페이스로 바뀌어요.</p>
      )}
      <div className={styles.inviteRow}>
        <div className="field">
          <label htmlFor={ids.name} className="field-label">
            이름
          </label>
          <input
            id={ids.name}
            className="input"
            required
            autoComplete="off"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor={ids.email} className="field-label">
            이메일
          </label>
          <input
            id={ids.email}
            className="input"
            type="email"
            required
            autoComplete="off"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        <button type="submit" className="btn btn--primary" disabled={submitting || !name.trim() || !email.trim()}>
          {submitting ? '초대하는 중' : '초대'}
        </button>
      </div>
      {error !== undefined &&
        (isApiError(error, 409) ? (
          <Notice tone="warning">이미 이 워크스페이스의 멤버예요.</Notice>
        ) : (
          <ErrorNotice error={error} />
        ))}
      {invited && (
        <Notice>
          {invited.name}님을 초대했어요.{invited.becameTeam && ' 이제 팀 워크스페이스예요.'}
        </Notice>
      )}
    </form>
  )
}
