import { Faders, Info, Users } from '@phosphor-icons/react'
import { NavLink, Outlet } from 'react-router'
import { useWorkspaceContext } from '../hooks/useWorkspace'
import { paths } from '../lib/paths'
import styles from './SettingsLayout.module.css'

/**
 * 설정 (노션의 설정 창 구성): 왼쪽에 '내 설정'과 '워크스페이스' 두 묶음, 오른쪽에 고른 화면.
 * - 내 설정: 모든 워크스페이스에 똑같이 적용되는 환경설정 (화면 모드, 글씨 크기, 계정)
 * - 워크스페이스: 지금 워크스페이스에만 적용 (이름, 개인/팀, 멤버)
 * 휴대폰에서는 왼쪽 목록이 위쪽 가로 목록이 된다.
 */
export function SettingsLayout() {
  const context = useWorkspaceContext()
  const { workspace, me } = context

  return (
    <div className={`page ${styles.settings}`}>
      <nav className={styles.nav} aria-label="설정">
        <h2 className={styles.groupTitle}>{me?.name ? `${me.name}님` : '내 설정'}</h2>
        <ul className={styles.list}>
          <li>
            <NavLink to={paths.preferences(workspace.id)} className={styles.item}>
              <Faders aria-hidden="true" />
              환경설정
            </NavLink>
          </li>
        </ul>

        <h2 className={styles.groupTitle}>{workspace.name}</h2>
        <ul className={styles.list}>
          <li>
            <NavLink end to={paths.settings(workspace.id)} className={styles.item}>
              <Info aria-hidden="true" />
              일반
            </NavLink>
          </li>
          <li>
            <NavLink to={paths.members(workspace.id)} className={styles.item}>
              <Users aria-hidden="true" />
              멤버
            </NavLink>
          </li>
        </ul>
      </nav>

      <div className={styles.content}>
        {/* 하위 설정 화면도 워크스페이스 컨텍스트를 그대로 쓴다. */}
        <Outlet context={context} />
      </div>
    </div>
  )
}
