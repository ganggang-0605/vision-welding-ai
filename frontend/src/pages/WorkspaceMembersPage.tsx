import { useId, useState, type FormEvent } from 'react'
import { isApiError } from '../api/client'
import type { Workspace } from '../api/types'
import { inviteMember, listMembers } from '../api/workspaces'
import { AsyncView } from '../components/AsyncView'
import { ErrorNotice, Notice } from '../components/Notice'
import { PageHeader } from '../components/PageHeader'
import { useAsync } from '../hooks/useAsync'
import { useWorkspaceContext } from '../hooks/useWorkspace'
import { MEMBER_ROLE_LABEL, workspaceKindLabel } from '../lib/labels'
import styles from './WorkspaceMembersPage.module.css'

/**
 * 설정 > 워크스페이스 > 멤버: 목록과 초대. 개인 워크스페이스에 초대하면 백엔드가 팀 워크스페이스로 바꾼다.
 * TODO(인증): 지금은 누구나 초대할 수 있다. 로그인이 생기면 소유자만 초대할 수 있게 한다.
 */
export function WorkspaceMembersPage() {
  const { workspace, reloadWorkspace } = useWorkspaceContext()
  const members = useAsync((signal) => listMembers(workspace.id, signal), [workspace.id])

  const onInvited = () => {
    reloadWorkspace()
    members.reload()
  }

  return (
    <>
      <PageHeader title="멤버" documentTitle={`${workspace.name} 멤버`} description={workspaceKindLabel(workspace)} />
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
      <InviteForm workspace={workspace} onInvited={onInvited} />
    </>
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
