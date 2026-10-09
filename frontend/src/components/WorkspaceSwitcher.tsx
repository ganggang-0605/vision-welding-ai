import { useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router'
import { listWorkspaces } from '../api/workspaces'
import { useAsync } from '../hooks/useAsync'
import { paths } from '../lib/paths'
import { AsyncView } from './AsyncView'
import styles from './WorkspaceSwitcher.module.css'

interface WorkspaceSwitcherProps {
  workspaceId: string
  /** 현재 워크스페이스 이름 (불러오기 전에는 id) */
  name: string
}

/** 사이드바 맨 위 워크스페이스 전환 메뉴. 바깥을 누르거나 Esc 를 누르면 닫힌다. */
export function WorkspaceSwitcher({ workspaceId, name }: WorkspaceSwitcherProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const menuId = useId()

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
        <span className={styles.avatar} aria-hidden="true">
          {name.charAt(0)}
        </span>
        <span className={styles.name}>{name}</span>
        <span className="visually-hidden">워크스페이스 전환</span>
        <span className={styles.chevron} aria-hidden="true" />
      </button>
      {open && <WorkspaceMenu id={menuId} currentId={workspaceId} onSelect={() => setOpen(false)} />}
    </div>
  )
}

interface WorkspaceMenuProps {
  id: string
  currentId: string
  onSelect: () => void
}

function WorkspaceMenu({ id, currentId, onSelect }: WorkspaceMenuProps) {
  const workspaces = useAsync((signal) => listWorkspaces(signal), [])

  return (
    <div id={id} className={styles.menu}>
      <p className={styles.menuTitle}>워크스페이스</p>
      {/* TODO(인증): 멤버 기능이 생기면 내가 속한 워크스페이스만 보여 준다. */}
      <AsyncView state={workspaces} isEmpty={(list) => list.length === 0} empty="워크스페이스가 없습니다.">
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
                  <span className={styles.itemName}>{workspace.name}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </AsyncView>
      <Link className={styles.item} to={paths.newWorkspace()} onClick={onSelect}>
        + 새 워크스페이스
      </Link>
    </div>
  )
}
