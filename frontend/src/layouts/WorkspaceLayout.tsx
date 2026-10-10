import {
  BookOpen,
  FileText,
  House,
  List,
  MagnifyingGlass,
  Plus,
  Ruler,
  SidebarSimple,
  TreeStructure,
} from '@phosphor-icons/react'
import { useCallback, useEffect, useId, useState, type MouseEvent } from 'react'
import { Link, Navigate, NavLink, Outlet, useLocation } from 'react-router'
import { isApiError } from '../api/client'
import { listJobs } from '../api/jobs'
import { getMe } from '../api/users'
import { getWorkspace } from '../api/workspaces'
import { AccountMenu } from '../components/AccountMenu'
import { BackendStatus } from '../components/BackendStatus'
import { ErrorNotice } from '../components/Notice'
import { PageHeader } from '../components/PageHeader'
import { SearchDialog } from '../components/SearchDialog'
import { WorkspaceSwitcher } from '../components/WorkspaceSwitcher'
import { useAsync } from '../hooks/useAsync'
import { useRequiredParam } from '../hooks/useRequiredParam'
import type { WorkspaceOutletContext } from '../hooks/useWorkspace'
import { useAccounts } from '../lib/accounts'
import { DEFAULT_WORKSPACE_ID, paths, rememberWorkspaceId } from '../lib/paths'
import styles from './WorkspaceLayout.module.css'

const IS_APPLE = /Mac|iPhone|iPad/.test(navigator.userAgent)
const SEARCH_SHORTCUT = IS_APPLE ? '⌘K' : 'Ctrl K'
const SIDEBAR_SHORTCUT = IS_APPLE ? '⌘\\' : 'Ctrl \\'
const SIDEBAR_COLLAPSED_KEY = 'vwa:sidebar-collapsed'
/** 사이드바 '작업'에 보여 줄 최근 작업 수 (나머지는 홈의 작업 목록에서) */
const SIDEBAR_JOB_COUNT = 15

/** 데스크톱 사이드바를 접어 둔 상태는 이 브라우저에 기억한다 (노션처럼 다시 열어도 그대로). */
function readCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true'
  } catch {
    return false
  }
}

/**
 * 워크스페이스 화면 공통 레이아웃: 노션처럼 왼쪽 사이드바(워크스페이스 전환, 사전, 작업) + 본문(<Outlet />).
 * 워크스페이스·현재 사용자를 불러온 뒤 하위 페이지에 context 로 넘긴다 (페이지에서는 useWorkspace()).
 * 768px 미만에서는 사이드바가 메뉴 버튼 뒤로 접힌다.
 */
export function WorkspaceLayout() {
  const workspaceId = useRequiredParam('workspaceId')
  const { activeId } = useAccounts()
  const sidebarId = useId()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  // 데스크톱(768px 이상)에서 사이드바를 접었는지. 휴대폰에서는 sidebarOpen(서랍)만 쓴다.
  const [collapsed, setCollapsed] = useState(readCollapsed)
  const [searchOpen, setSearchOpen] = useState(false)

  const { pathname } = useLocation()
  const workspace = useAsync((signal) => getWorkspace(workspaceId, signal), [workspaceId])
  // 사이드바 작업 목록. 화면을 옮길 때마다 다시 읽어 새로 만든 작업·바뀐 이름이 바로 보이게 한다.
  const jobs = useAsync((signal) => listJobs(workspaceId, {}, signal), [workspaceId, pathname])
  const jobList = jobs.data?.every((job) => job.workspace_id === workspaceId) ? jobs.data : undefined
  // 계정을 바꾸면(전환 메뉴) 현재 사용자를 다시 불러온다.
  const me = useAsync((signal) => getMe(signal), [activeId])
  // useAsync 는 다시 불러오는 동안 직전 값을 유지하므로, 워크스페이스를 바꾼 직후에는 이전 워크스페이스 값을 쓰지 않는다.
  const current = workspace.data?.id === workspaceId ? workspace.data : undefined
  // 없는 워크스페이스면 본문은 안내 화면, 사이드바는 전환 메뉴만 보여 준다.
  const notFound = !workspace.loading && isApiError(workspace.error, 404)

  useEffect(() => {
    if (current && activeId) rememberWorkspaceId(activeId, current.id)
  }, [current, activeId])

  const openSearch = useCallback(() => {
    setSidebarOpen(false)
    setSearchOpen(true)
  }, [])
  const closeSearch = useCallback(() => setSearchOpen(false), [])

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed))
    } catch {
      // 기억하지 못해도 이번 방문 동안은 동작한다.
    }
  }, [collapsed])

  // ⌘K / Ctrl+K: 검색 열기·닫기, ⌘\ / Ctrl+\: 사이드바 접기·펴기, Esc: 모바일 사이드바 닫기
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setSidebarOpen(false)
        setSearchOpen((value) => !value)
      } else if ((event.metaKey || event.ctrlKey) && event.key === '\\') {
        event.preventDefault()
        setCollapsed((value) => !value)
      } else if (event.key === 'Escape') {
        setSidebarOpen(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  // 화면을 옮기면 모바일 사이드바를 닫는다.
  const closeSidebarOnLink = (event: MouseEvent<HTMLElement>) => {
    if ((event.target as HTMLElement).closest('a')) setSidebarOpen(false)
  }

  // 모든 계정에서 로그아웃했으면 계정 고르기로.
  if (!activeId) return <Navigate replace to={paths.login()} />

  return (
    <div className={styles.shell} data-collapsed={collapsed}>
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
          <List size={20} aria-hidden="true" />
          <span className="visually-hidden">메뉴</span>
        </button>
        <span className={styles.mobileTitle}>{current?.name ?? ''}</span>
        {!notFound && (
          <button type="button" className={styles.iconButton} onClick={openSearch} aria-haspopup="dialog">
            <MagnifyingGlass size={20} aria-hidden="true" />
            <span className="visually-hidden">검색</span>
          </button>
        )}
      </header>

      {sidebarOpen && <div className={styles.backdrop} aria-hidden="true" onClick={() => setSidebarOpen(false)} />}

      <aside id={sidebarId} className={styles.sidebar} data-open={sidebarOpen} onClick={closeSidebarOnLink}>
        <div className={styles.sidebarTop}>
          <WorkspaceSwitcher workspaceId={workspaceId} workspace={current} />
          <button
            type="button"
            className={styles.collapseButton}
            onClick={() => setCollapsed(true)}
            title={`사이드바 닫기 (${SIDEBAR_SHORTCUT})`}
          >
            <SidebarSimple size={17} aria-hidden="true" />
            <span className="visually-hidden">사이드바 닫기</span>
          </button>
        </div>

        {!notFound && (
          <nav className={styles.nav} aria-label="워크스페이스 메뉴">
            <ul className={styles.navList}>
              <li>
                <NavLink end to={paths.workspaceHome(workspaceId)} className={styles.navItem}>
                  <House aria-hidden="true" />
                  워크스페이스 홈
                </NavLink>
              </li>
              <li>
                <button type="button" className={styles.searchField} onClick={openSearch} aria-haspopup="dialog">
                  <MagnifyingGlass size={15} aria-hidden="true" />
                  검색
                  <kbd className="kbd">{SEARCH_SHORTCUT}</kbd>
                </button>
              </li>
            </ul>

            <h2 className={styles.sectionTitle}>워크스페이스 사전</h2>
            <ul className={styles.navList}>
              <li>
                <NavLink to={paths.symbols(workspaceId)} className={styles.navItem}>
                  <BookOpen aria-hidden="true" />
                  문자·기호 사전
                </NavLink>
              </li>
              <li>
                <NavLink to={paths.standards(workspaceId)} className={styles.navItem}>
                  <Ruler aria-hidden="true" />
                  용접 기준 사전
                </NavLink>
              </li>
              <li>
                <NavLink to={paths.assemblyPaths(workspaceId)} className={styles.navItem}>
                  <TreeStructure aria-hidden="true" />
                  조립 경로 사전
                </NavLink>
              </li>
            </ul>

            <div className={styles.sectionHead}>
              <h2 className={styles.sectionTitle}>작업</h2>
              <Link className={styles.sectionAction} to={paths.newJob(workspaceId)} title="새 작업">
                <Plus size={14} weight="bold" aria-hidden="true" />
                <span className="visually-hidden">새 작업</span>
              </Link>
            </div>
            <ul className={styles.navList}>
              <li>
                <NavLink to={paths.newJob(workspaceId)} className={styles.navItem}>
                  <Plus aria-hidden="true" />
                  새 작업
                </NavLink>
              </li>
              {jobList?.slice(0, SIDEBAR_JOB_COUNT).map((job) => (
                <li key={job.id}>
                  <NavLink to={paths.job(workspaceId, job.id)} className={styles.navItem}>
                    <FileText aria-hidden="true" />
                    <span className={styles.ellipsis}>{job.name}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
            {jobs.error !== undefined ? (
              <p className={styles.navHint}>작업을 불러오지 못했어요</p>
            ) : (
              jobList &&
              jobList.length > SIDEBAR_JOB_COUNT && (
                <Link className={styles.navHint} to={paths.workspaceHome(workspaceId)}>
                  작업 {jobList.length}개 모두 보기
                </Link>
              )
            )}
          </nav>
        )}

        {/* 작업과 상관없는 내 계정·환경설정은 클로드처럼 맨 아래. 팀원 초대는 맨 위 워크스페이스 메뉴에 있다. */}
        <footer className={styles.sidebarFooter}>
          <BackendStatus />
          <AccountMenu workspaceId={workspaceId} me={me.data} />
        </footer>
      </aside>

      {collapsed && (
        <button
          type="button"
          className={styles.expandButton}
          onClick={() => setCollapsed(false)}
          title={`사이드바 열기 (${SIDEBAR_SHORTCUT})`}
        >
          <SidebarSimple size={18} aria-hidden="true" />
          <span className="visually-hidden">사이드바 열기</span>
        </button>
      )}

      <main id="main" className={styles.main} tabIndex={-1}>
        {notFound ? (
          <WorkspaceNotFound workspaceId={workspaceId} />
        ) : current ? (
          // 다시 불러오는 동안(이름 변경 뒤)에는 직전 값으로 본문을 유지해 깜빡이지 않게 한다.
          <Outlet
            context={
              {
                workspace: current,
                me: me.data,
                reloadWorkspace: workspace.reload,
              } satisfies WorkspaceOutletContext
            }
          />
        ) : workspace.error !== undefined ? (
          <div className="page">
            <ErrorNotice error={workspace.error} onRetry={workspace.reload} />
          </div>
        ) : (
          <div className="page">
            <div className="skeleton" role="status" aria-label="불러오는 중">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}
      </main>

      <SearchDialog
        workspaceId={workspaceId}
        open={searchOpen && !notFound}
        onClose={closeSearch}
        key={workspaceId}
      />
    </div>
  )
}

function WorkspaceNotFound({ workspaceId }: { workspaceId: string }) {
  return (
    <div className="page">
      <PageHeader
        title="워크스페이스를 찾을 수 없어요"
        description={`'${workspaceId}' 워크스페이스가 없거나 삭제됐어요.`}
      />
      <p className="button-row">
        <Link className="btn" to={paths.workspaceHome(DEFAULT_WORKSPACE_ID)}>
          데모 워크스페이스 열기
        </Link>
        <Link className="btn btn--primary" to={paths.newWorkspace()}>
          새 워크스페이스 만들기
        </Link>
      </p>
    </div>
  )
}
