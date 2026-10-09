import { useCallback, useEffect, useId, useState, type MouseEvent } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router'
import { isApiError } from '../api/client'
import { listJobs } from '../api/jobs'
import { getWorkspace } from '../api/workspaces'
import { AsyncView } from '../components/AsyncView'
import { BackendStatus } from '../components/BackendStatus'
import { PageHeader } from '../components/PageHeader'
import { SearchDialog } from '../components/SearchDialog'
import { WorkspaceSwitcher } from '../components/WorkspaceSwitcher'
import { useAsync } from '../hooks/useAsync'
import { useRequiredParam } from '../hooks/useRequiredParam'
import type { WorkspaceOutletContext } from '../hooks/useWorkspace'
import { DEFAULT_WORKSPACE_ID, paths } from '../lib/paths'
import styles from './WorkspaceLayout.module.css'

/** 사이드바 '최근 작업'에 보여 줄 개수 */
const RECENT_JOB_COUNT = 5

const SEARCH_SHORTCUT = /Mac|iPhone|iPad/.test(navigator.userAgent) ? '⌘K' : 'Ctrl K'

/**
 * 워크스페이스 화면 공통 레이아웃: Notion 스타일 왼쪽 사이드바 + 본문(<Outlet />).
 * 워크스페이스를 불러온 뒤 하위 페이지에 context 로 넘긴다 (페이지에서는 useWorkspace()).
 * 768px 미만에서는 사이드바가 메뉴 버튼 뒤로 접힌다.
 */
export function WorkspaceLayout() {
  const workspaceId = useRequiredParam('workspaceId')
  const { pathname } = useLocation()
  const sidebarId = useId()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)

  const workspace = useAsync((signal) => getWorkspace(workspaceId, signal), [workspaceId])
  // 다른 화면에서 작업을 만들거나 승인한 결과가 반영되도록 화면을 옮길 때마다 다시 불러온다.
  const recentJobs = useAsync((signal) => listJobs(workspaceId, {}, signal), [workspaceId, pathname])
  // useAsync 는 다시 불러오는 동안 직전 값을 유지하므로, 워크스페이스를 바꾼 직후에는 이전 워크스페이스 값을 쓰지 않는다.
  const workspaceName = workspace.data?.id === workspaceId ? workspace.data.name : workspaceId
  // 없는 워크스페이스면 본문은 안내 화면, 사이드바는 전환 메뉴만 보여 준다 (하위 메뉴·최근 작업도 모두 404).
  const notFound = !workspace.loading && isApiError(workspace.error, 404)
  const recent = recentJobs.data?.some((job) => job.workspace_id !== workspaceId) ? undefined : recentJobs.data

  const openSearch = useCallback(() => {
    setSidebarOpen(false)
    setSearchOpen(true)
  }, [])
  const closeSearch = useCallback(() => setSearchOpen(false), [])

  // ⌘K / Ctrl+K: 검색 열기·닫기, Esc: 모바일 사이드바 닫기
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setSidebarOpen(false)
        setSearchOpen((value) => !value)
      } else if (event.key === 'Escape') {
        setSidebarOpen(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  // 모바일: 사이드바의 링크를 누르면 사이드바를 닫는다.
  const closeSidebarOnLink = (event: MouseEvent<HTMLElement>) => {
    if ((event.target as HTMLElement).closest('a')) setSidebarOpen(false)
  }

  return (
    <div className={styles.shell}>
      <a className="skip-link" href="#main">
        본문으로 건너뛰기
      </a>

      <header className={styles.mobileBar}>
        <button
          type="button"
          className={styles.iconButton}
          aria-expanded={sidebarOpen}
          aria-controls={sidebarId}
          onClick={() => setSidebarOpen((value) => !value)}
        >
          <span aria-hidden="true">☰</span>
          <span className="visually-hidden">메뉴</span>
        </button>
        <span className={styles.mobileTitle}>{workspaceName}</span>
        {!notFound && (
          <button type="button" className={styles.iconButton} onClick={openSearch} aria-haspopup="dialog">
            검색
          </button>
        )}
      </header>

      {sidebarOpen && <div className={styles.backdrop} aria-hidden="true" onClick={() => setSidebarOpen(false)} />}

      <aside id={sidebarId} className={styles.sidebar} data-open={sidebarOpen} onClick={closeSidebarOnLink}>
        <WorkspaceSwitcher workspaceId={workspaceId} name={workspaceName} />

        {!notFound && (
          <nav className={styles.nav} aria-label="워크스페이스 메뉴">
            <ul className={styles.navList}>
              <li>
                <button type="button" className={styles.navItem} onClick={openSearch} aria-haspopup="dialog">
                  검색
                  <kbd className="kbd">{SEARCH_SHORTCUT}</kbd>
                </button>
              </li>
              <li>
                <NavLink end to={paths.workspaceHome(workspaceId)} className={styles.navItem}>
                  홈
                </NavLink>
              </li>
              <li>
                <NavLink to={paths.newJob(workspaceId)} className={styles.navItem}>
                  새 작업
                </NavLink>
              </li>
            </ul>

            <h2 className={styles.sectionTitle}>최근 작업</h2>
            <ul className={styles.navList}>
              {recentJobs.error !== undefined ? (
                <li className={styles.navHint}>불러오지 못했습니다.</li>
              ) : recent === undefined ? (
                <li className={styles.navHint}>불러오는 중…</li>
              ) : recent.length === 0 ? (
                <li className={styles.navHint}>아직 작업이 없습니다.</li>
              ) : (
                recent.slice(0, RECENT_JOB_COUNT).map((job) => (
                  <li key={job.id}>
                    <NavLink to={paths.job(workspaceId, job.id)} className={styles.navItem}>
                      <span className={styles.ellipsis}>{job.name}</span>
                    </NavLink>
                  </li>
                ))
              )}
            </ul>

            <h2 className={styles.sectionTitle}>워크스페이스 DB</h2>
            <ul className={styles.navList}>
              <li>
                <NavLink to={paths.symbols(workspaceId)} className={styles.navItem}>
                  문자/기호 사전
                </NavLink>
              </li>
              <li>
                <NavLink to={paths.assemblyTree(workspaceId)} className={styles.navItem}>
                  조립 트리
                </NavLink>
              </li>
              <li>
                <NavLink to={paths.standards(workspaceId)} className={styles.navItem}>
                  용접 기준
                  <span className="badge" title="모든 워크스페이스가 함께 쓰는 공식 기준">
                    공통
                  </span>
                </NavLink>
              </li>
            </ul>
          </nav>
        )}

        <footer className={styles.sidebarFooter}>
          <BackendStatus />
        </footer>
      </aside>

      <main id="main" className={styles.main} tabIndex={-1}>
        {notFound ? (
          <WorkspaceNotFound workspaceId={workspaceId} />
        ) : (
          <AsyncView state={workspace}>
            {(data) => <Outlet context={{ workspace: data } satisfies WorkspaceOutletContext} />}
          </AsyncView>
        )}
      </main>

      <SearchDialog workspaceId={workspaceId} open={searchOpen && !notFound} onClose={closeSearch} />
    </div>
  )
}

function WorkspaceNotFound({ workspaceId }: { workspaceId: string }) {
  return (
    <div className="page">
      <PageHeader
        title="워크스페이스를 찾을 수 없습니다"
        description={`'${workspaceId}' 워크스페이스가 없거나 삭제되었습니다.`}
      />
      <p className="button-row">
        <Link className="btn" to={paths.workspaceHome(DEFAULT_WORKSPACE_ID)}>
          데모 워크스페이스로
        </Link>
        <Link className="btn btn--primary" to={paths.newWorkspace()}>
          새 워크스페이스 만들기
        </Link>
      </p>
    </div>
  )
}
