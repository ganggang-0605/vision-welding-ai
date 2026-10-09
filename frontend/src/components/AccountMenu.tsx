import { CaretUpDown, Faders, Gear, SignOut } from '@phosphor-icons/react'
import { useEffect, useId, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import type { User } from '../api/types'
import { signOut, useAccounts } from '../lib/accounts'
import { paths } from '../lib/paths'
import { THEME_OPTIONS, useThemePreference } from '../lib/preferences'
import styles from './AccountMenu.module.css'

interface AccountMenuProps {
  workspaceId: string
  me: User | undefined
}

/**
 * 사이드바 맨 아래 내 계정 (클로드처럼). 작업과 상관없는 환경설정·화면 모드·로그아웃을 여기에 모은다.
 * 메뉴는 위로 열리고, 바깥을 누르거나 Esc 를 누르면 닫힌다.
 */
export function AccountMenu({ workspaceId, me }: AccountMenuProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const menuId = useId()
  const navigate = useNavigate()
  const { activeId } = useAccounts()
  const [theme, setTheme] = useThemePreference()

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

  const signOutHere = () => {
    if (!activeId) return
    signOut(activeId)
    setOpen(false)
    // 남은 계정의 마지막 워크스페이스로 (없으면 계정 고르기).
    navigate('/')
  }

  return (
    <div className={styles.root} ref={rootRef}>
      {open && (
        <div id={menuId} className={styles.menu}>
          <p className={styles.email}>{me?.email}</p>
          <ul className={styles.list}>
            <li>
              <Link className={styles.item} to={paths.preferences(workspaceId)} onClick={() => setOpen(false)}>
                <Faders size={17} aria-hidden="true" />
                환경설정
              </Link>
            </li>
            <li>
              <Link className={styles.item} to={paths.settings(workspaceId)} onClick={() => setOpen(false)}>
                <Gear size={17} aria-hidden="true" />
                워크스페이스 설정
              </Link>
            </li>
          </ul>
          <div className={styles.theme}>
            <span id={`${menuId}-theme`}>화면 모드</span>
            <div className="segmented" role="group" aria-labelledby={`${menuId}-theme`}>
              {THEME_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={theme === option.value}
                  onClick={() => setTheme(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
          <button type="button" className={`${styles.item} ${styles.signOut}`} onClick={signOutHere}>
            <SignOut size={17} aria-hidden="true" />
            로그아웃
          </button>
        </div>
      )}
      <button
        type="button"
        className={styles.trigger}
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((value) => !value)}
      >
        <span className={styles.avatar} aria-hidden="true">
          {me?.name.charAt(0)}
        </span>
        <span className={styles.who}>
          <span className={styles.name}>{me?.name ?? '내 계정'}</span>
          <span className={styles.sub}>{me?.email}</span>
        </span>
        <span className="visually-hidden">계정 메뉴</span>
        <CaretUpDown className={styles.chevron} size={14} aria-hidden="true" />
      </button>
    </div>
  )
}
