import { CaretUpDown, Check, Gear, Plus, SignOut, UserCirclePlus, UserPlus } from '@phosphor-icons/react'
import { useEffect, useId, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import type { Workspace } from '../api/types'
import { getMe } from '../api/users'
import { listWorkspaces } from '../api/workspaces'
import { useAsync } from '../hooks/useAsync'
import { signOut, signOutAll, switchAccount, useAccounts } from '../lib/accounts'
import { workspaceKindLabel } from '../lib/labels'
import { paths } from '../lib/paths'
import styles from './WorkspaceSwitcher.module.css'

interface WorkspaceSwitcherProps {
  workspaceId: string
  /** 현재 워크스페이스 (불러오기 전이면 undefined) */
  workspace: Workspace | undefined
}

/**
 * 사이드바 맨 위 워크스페이스 전환 메뉴 (노션과 같은 구성).
 * 위: 지금 워크스페이스, 설정·팀원 초대·계정 추가 / 가운데: 로그인한 계정마다 워크스페이스 목록과 새 워크스페이스 /
 * 아래: 모든 계정에서 로그아웃. 바깥을 누르거나 Esc 를 누르면 닫힌다.
 */
export function WorkspaceSwitcher({ workspaceId, workspace }: WorkspaceSwitcherProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const menuId = useId()
  const name = workspace?.name ?? workspaceId

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  return (
    <div className={styles.root} ref={rootRef}>
      <button
        type="button"
        className={styles.trigger}
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((value) => !value)}
      >
        <WorkspaceAvatar name={name} />
        <span className={styles.name}>{name}</span>
        <span className="visually-hidden">워크스페이스 전환</span>
        <CaretUpDown className={styles.chevron} size={14} aria-hidden="true" />
      </button>
      {open && <WorkspaceMenu id={menuId} currentId={workspaceId} current={workspace} onClose={() => setOpen(false)} />}
    </div>
  )
}

export function WorkspaceAvatar({ name, size = 'small' }: { name: string; size?: 'small' | 'large' }) {
  return (
    <span className={size === 'large' ? `${styles.avatar} ${styles.avatarLarge}` : styles.avatar} aria-hidden="true">
      {name.charAt(0)}
    </span>
  )
}

interface WorkspaceMenuProps {
  id: string
  currentId: string
  current: Workspace | undefined
  onClose: () => void
}

function WorkspaceMenu({ id, currentId, current, onClose }: WorkspaceMenuProps) {
  const navigate = useNavigate()
  const { accountIds, activeId } = useAccounts()

  const signOutEverywhere = () => {
    signOutAll()
    onClose()
    navigate(paths.login())
  }

  return (
    <div id={id} className={styles.menu}>
      {current && (
        <div className={styles.current}>
          <WorkspaceAvatar name={current.name} size="large" />
          <div className={styles.currentText}>
            <span className={styles.currentName}>{current.name}</span>
            <span className={styles.meta}>{workspaceKindLabel(current)}</span>
          </div>
        </div>
      )}

      <ul className={styles.list}>
        <li>
          <Link className={styles.item} to={paths.settings(currentId)} onClick={onClose}>
            <Gear className={styles.itemIcon} size={17} aria-hidden="true" />
            설정
          </Link>
        </li>
        <li>
          <Link className={styles.item} to={paths.members(currentId)} onClick={onClose}>
            <UserPlus className={styles.itemIcon} size={17} aria-hidden="true" />
            팀원 초대
          </Link>
        </li>
        <li>
          <Link className={styles.item} to={paths.login('add')} onClick={onClose}>
            <UserCirclePlus className={styles.itemIcon} size={17} aria-hidden="true" />
            계정 추가하기
          </Link>
        </li>
      </ul>

      {accountIds.map((accountId) => (
        <AccountSection
          key={accountId}
          accountId={accountId}
          active={accountId === activeId}
          currentId={currentId}
          onClose={onClose}
        />
      ))}

      <button type="button" className={`${styles.item} ${styles.footer}`} onClick={signOutEverywhere}>
        모든 계정에서 로그아웃
      </button>
    </div>
  )
}

interface AccountSectionProps {
  accountId: string
  /** 지금 쓰는 계정이면 true */
  active: boolean
  currentId: string
  onClose: () => void
}

/** 계정 하나: 이메일 + 그 계정의 워크스페이스 + 새 워크스페이스. 다른 계정의 워크스페이스를 누르면 그 계정으로 바뀐다. */
function AccountSection({ accountId, active, currentId, onClose }: AccountSectionProps) {
  const navigate = useNavigate()
  const user = useAsync((signal) => getMe(signal, accountId), [accountId])
  const workspaces = useAsync((signal) => listWorkspaces(signal, accountId), [accountId])

  const selectThisAccount = () => {
    switchAccount(accountId)
    onClose()
  }

  const signOutHere = () => {
    signOut(accountId)
    onClose()
    // 지금 쓰던 계정에서 나가면 남은 계정의 마지막 워크스페이스로 (없으면 계정 고르기).
    if (active) navigate('/')
  }

  return (
    <section className={styles.account} aria-label={user.data?.email ?? accountId}>
      <div className={styles.accountHead}>
        <span className={styles.email}>{user.data?.email ?? accountId}</span>
        <button type="button" className={styles.signOut} onClick={signOutHere} title="이 계정에서 로그아웃">
          <SignOut size={14} aria-hidden="true" />
          <span className="visually-hidden">{user.data?.email ?? accountId} 로그아웃</span>
        </button>
      </div>
      {workspaces.error !== undefined ? (
        <p className={styles.hint}>워크스페이스를 불러오지 못했어요</p>
      ) : workspaces.data === undefined ? (
        <p className={styles.hint}>불러오는 중</p>
      ) : (
        <ul className={styles.list}>
          {workspaces.data.map((workspace) => {
            const isCurrent = active && workspace.id === currentId
            return (
              <li key={workspace.id}>
                <Link
                  className={styles.item}
                  to={paths.workspaceHome(workspace.id)}
                  aria-current={isCurrent ? 'page' : undefined}
                  title={workspace.name}
                  onClick={selectThisAccount}
                >
                  <WorkspaceAvatar name={workspace.name} />
                  <span className={styles.itemName}>{workspace.name}</span>
                  {workspace.kind === 'team' && <span className={styles.tag}>팀</span>}
                  {isCurrent && <Check className={styles.check} size={15} weight="bold" aria-hidden="true" />}
                </Link>
              </li>
            )
          })}
          <li>
            <Link className={`${styles.item} ${styles.create}`} to={paths.newWorkspace()} onClick={selectThisAccount}>
              <Plus className={styles.itemIcon} size={15} weight="bold" aria-hidden="true" />새 워크스페이스
            </Link>
          </li>
        </ul>
      )}
    </section>
  )
}
