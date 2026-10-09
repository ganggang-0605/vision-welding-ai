import { CaretRight, TreeStructure } from '@phosphor-icons/react'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { listUsers } from '../api/users'
import { listWorkspaces } from '../api/workspaces'
import { AsyncView } from '../components/AsyncView'
import { ErrorNotice } from '../components/Notice'
import { PageHeader } from '../components/PageHeader'
import { useAsync } from '../hooks/useAsync'
import { signIn, useAccounts } from '../lib/accounts'
import { paths, readLastWorkspaceId } from '../lib/paths'
import styles from './LoginPage.module.css'

/**
 * 계정 고르기 (/login, 계정 추가는 /login?mode=add). 사이드바 없는 단독 화면.
 * 로그인 기능이 생기기 전까지 비밀번호 없이 데모 계정 중 하나로 들어간다 (TODO 인증).
 * 고른 계정의 마지막 워크스페이스로, 처음이면 첫 워크스페이스로, 하나도 없으면 워크스페이스 만들기로 간다.
 */
export function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const adding = searchParams.get('mode') === 'add'
  const { accountIds } = useAccounts()
  const users = useAsync((signal) => listUsers(signal), [])
  const [pendingId, setPendingId] = useState<string>()
  const [error, setError] = useState<unknown>()

  const choose = async (userId: string) => {
    setPendingId(userId)
    setError(undefined)
    try {
      const workspaces = await listWorkspaces(undefined, userId)
      signIn(userId)
      const last = readLastWorkspaceId(userId)
      const target = workspaces.find((workspace) => workspace.id === last) ?? workspaces[0]
      navigate(target ? paths.workspaceHome(target.id) : paths.newWorkspace())
    } catch (err) {
      setError(err)
      setPendingId(undefined)
    }
  }

  return (
    <div className={styles.screen}>
      <span className={styles.appIcon} aria-hidden="true">
        <TreeStructure size={30} />
      </span>
      <PageHeader
        title={adding ? '계정 추가하기' : 'Vision Welding AI'}
        description="로그인 기능이 준비될 때까지 데모 계정으로 들어가요."
      />

      <AsyncView state={users} isEmpty={(list) => list.length === 0} empty="데모 계정이 없어요.">
        {(list) => (
          <ul className="group">
            {list.map((user) => {
              const signedIn = accountIds.includes(user.id)
              return (
                <li key={user.id}>
                  <button
                    type="button"
                    className={styles.account}
                    onClick={() => choose(user.id)}
                    disabled={pendingId !== undefined}
                  >
                    <span className={styles.avatar} aria-hidden="true">
                      {user.name.charAt(0)}
                    </span>
                    <span className={styles.text}>
                      <span>{user.name}</span>
                      <span className={styles.email}>{user.email}</span>
                    </span>
                    {signedIn && <span className="status">로그인됨</span>}
                    <CaretRight className={styles.chevron} size={14} weight="bold" aria-hidden="true" />
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </AsyncView>

      {error !== undefined && <ErrorNotice error={error} />}

      {adding && accountIds.length > 0 && (
        <Link className={`btn btn--plain ${styles.back}`} to="/">
          취소
        </Link>
      )}
    </div>
  )
}
