import { CaretUpDown, Check, Gear, Plus, UserPlus } from '@phosphor-icons/react'
import { useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router'
import type { User, Workspace } from '../api/types'
import { listWorkspaces } from '../api/workspaces'
import { useAsync } from '../hooks/useAsync'
import { workspaceKindLabel } from '../lib/labels'
import { paths } from '../lib/paths'
import { AsyncView } from './AsyncView'
import styles from './WorkspaceSwitcher.module.css'

interface WorkspaceSwitcherProps {
  workspaceId: string
  /** 현재 워크스페이스 (불러오기 전이면 undefined) */
  workspace: Workspace | undefined
  me: User | undefined
}

/**
 * 사이드바 맨 위 워크스페이스 전환 메뉴 (노션과 같은 구성).
 * 위: 지금 워크스페이스 + 설정·초대 / 가운데: 내 계정의 워크스페이스 목록 / 아래: 새 워크스페이스.
 * 바깥을 누르거나 Esc 를 누르면 닫힌다.
 */
export function WorkspaceSwitcher({ workspaceId, workspace, me }: WorkspaceSwitcherProps) {
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
      {open && (
        <WorkspaceMenu
          id={menuId}
          currentId={workspaceId}
          current={workspace}
          me={me}
          onSelect={() => setOpen(false)}
        />
      )}
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
  me: User | undefined
  onSelect: () => void
}

function WorkspaceMenu({ id, currentId, current, me, onSelect }: WorkspaceMenuProps) {
  const workspaces = useAsync((signal) => listWorkspaces(signal), [])

  return (
    <div id={id} className={styles.menu}>
      {current && (
        <div className={styles.currentBlock}>
          <div className={styles.current}>
            <WorkspaceAvatar name={current.name} size="large" />
            <div className={styles.currentText}>
              <span className={styles.currentName}>{current.name}</span>
              <span className={styles.currentMeta}>{workspaceKindLabel(current)}</span>
            </div>
          </div>
          <div className={styles.currentActions}>
            <Link className="btn btn--small" to={paths.settings(current.id)} onClick={onSelect}>
              <Gear size={14} aria-hidden="true" />
              설정
            </Link>
            <Link className="btn btn--small" to={`${paths.settings(current.id)}#members`} onClick={onSelect}>
              <UserPlus size={14} aria-hidden="true" />
              {current.kind === 'personal' ? '팀원 초대' : '멤버 초대'}
            </Link>
          </div>
        </div>
      )}

      {/* TODO(인증): 로그인이 생기면 계정별로 묶고, 다른 계정 추가·전환을 붙인다. */}
      <p className={styles.menuTitle}>{me?.email ?? '내 워크스페이스'}</p>
      <AsyncView state={workspaces} isEmpty={(list) => list.length === 0} empty="워크스페이스가 없어요.">
        {(list) => (
          <ul className={styles.list}>
            {list.map((workspace) => (
              <li key={workspace.id}>
                <Link
                  className={styles.item}
                  to={paths.workspaceHome(workspace.id)}
                  aria-current={workspace.id === currentId ? 'page' : undefined}
                  title={workspace.name}
                  onClick={onSelect}
                >
                  <WorkspaceAvatar name={workspace.name} />
                  <span className={styles.itemText}>
                    <span className={styles.itemName}>{workspace.name}</span>
                    <span className={styles.itemMeta}>{workspaceKindLabel(workspace)}</span>
                  </span>
                  {workspace.id === currentId && (
                    <Check className={styles.check} size={15} weight="bold" aria-hidden="true" />
                  )}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </AsyncView>
      <Link className={styles.item} to={paths.newWorkspace()} onClick={onSelect}>
        <span className={styles.plusTile} aria-hidden="true">
          <Plus size={13} weight="bold" />
        </span>
        새 워크스페이스
      </Link>
    </div>
  )
}
