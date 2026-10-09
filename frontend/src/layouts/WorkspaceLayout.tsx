import {
  BookOpen,
  Cube,
  CaretRight,
  House,
  List,
  ListBullets,
  MagnifyingGlass,
  Plus,
  Ruler,
  SidebarSimple,
  TreeStructure,
} from '@phosphor-icons/react'
import { useCallback, useEffect, useId, useState, type MouseEvent } from 'react'
import { Link, Navigate, NavLink, Outlet, useParams } from 'react-router'
import { isApiError } from '../api/client'
import { listProjects } from '../api/projects'
import type { Project } from '../api/types'
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

/** 데스크톱 사이드바를 접어 둔 상태는 이 브라우저에 기억한다 (노션처럼 다시 열어도 그대로). */
function readCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true'
  } catch {
    return false
  }
}

/**
 * 워크스페이스 화면 공통 레이아웃: 노션처럼 왼쪽 사이드바(워크스페이스 전환, 프로젝트 트리) + 본문(<Outlet />).
 * 워크스페이스·프로젝트 목록·현재 사용자를 불러온 뒤 하위 페이지에 context 로 넘긴다 (페이지에서는 useWorkspace()).
 * 768px 미만에서는 사이드바가 메뉴 버튼 뒤로 접힌다.
 */
export function WorkspaceLayout() {
  const workspaceId = useRequiredParam('workspaceId')
  const { projectId } = useParams()
  const { activeId } = useAccounts()
  const sidebarId = useId()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  // 데스크톱(768px 이상)에서 사이드바를 접었는지. 휴대폰에서는 sidebarOpen(서랍)만 쓴다.
  const [collapsed, setCollapsed] = useState(readCollapsed)
  const [searchOpen, setSearchOpen] = useState(false)

  const workspace = useAsync((signal) => getWorkspace(workspaceId, signal), [workspaceId])
  const projects = useAsync((signal) => listProjects(workspaceId, signal), [workspaceId])
  // 계정을 바꾸면(전환 메뉴) 현재 사용자를 다시 불러온다.
  const me = useAsync((signal) => getMe(signal), [activeId])
  // useAsync 는 다시 불러오는 동안 직전 값을 유지하므로, 워크스페이스를 바꾼 직후에는 이전 워크스페이스 값을 쓰지 않는다.
  const current = workspace.data?.id === workspaceId ? workspace.data : undefined
  const projectList = projects.data?.every((project) => project.workspace_id === workspaceId) ? projects.data : undefined
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

            <div className={styles.sectionHead}>
              <h2 className={styles.sectionTitle}>작업</h2>
              <Link className={styles.sectionAction} to={paths.newProject(workspaceId)} title="새 블록">
                <Plus size={14} weight="bold" aria-hidden="true" />
                <span className="visually-hidden">새 블록</span>
              </Link>
            </div>
            {projects.error !== undefined ? (
              <p className={styles.navHint}>불러오지 못했어요</p>
            ) : projectList === undefined ? (
              <p className={styles.navHint}>불러오는 중</p>
            ) : projectList.length === 0 ? (
              <Link className={styles.navHint} to={paths.newProject(workspaceId)}>
                첫 블록을 추가해 보세요
              </Link>
            ) : (
              <ProjectTree
                key={workspaceId}
                workspaceId={workspaceId}
                projects={projectList}
                activeProjectId={projectId}
              />
            )}

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
                  용접 기준
                </NavLink>
              </li>
            </ul>
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
        ) : current && projectList ? (
          // 다시 불러오는 동안(이름 변경·프로젝트 추가 뒤)에는 직전 값으로 본문을 유지해 깜빡이지 않게 한다.
          <Outlet
            context={
              {
                workspace: current,
                projects: projectList,
                me: me.data,
                reloadWorkspace: workspace.reload,
                reloadProjects: projects.reload,
              } satisfies WorkspaceOutletContext
            }
          />
        ) : workspace.error !== undefined || projects.error !== undefined ? (
          <div className="page">
            <ErrorNotice
              error={workspace.error ?? projects.error}
              onRetry={() => {
                workspace.reload()
                projects.reload()
              }}
            />
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
        projects={projectList ?? []}
        open={searchOpen && !notFound}
        onClose={closeSearch}
        key={workspaceId}
      />
    </div>
  )
}

interface ProjectTreeProps {
  workspaceId: string
  projects: Project[]
  activeProjectId: string | undefined
}

/** 노션 페이지 트리처럼 프로젝트를 펼치면 작업·조립 트리가 보인다. 지금 보고 있는 프로젝트는 자동으로 펼친다. */
function ProjectTree({ workspaceId, projects, activeProjectId }: ProjectTreeProps) {
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set(activeProjectId ? [activeProjectId] : []))
  const [lastActive, setLastActive] = useState(activeProjectId)
  if (activeProjectId !== lastActive) {
    // 다른 프로젝트로 이동하면 그 프로젝트를 펼친다 (렌더 중 상태 조정, effect 없이).
    setLastActive(activeProjectId)
    if (activeProjectId && !expanded.has(activeProjectId)) setExpanded(new Set([...expanded, activeProjectId]))
  }

  const toggle = (id: string) => {
    const next = new Set(expanded)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setExpanded(next)
  }

  return (
    <ul className={styles.navList}>
      {projects.map((project) => {
        const open = expanded.has(project.id)
        const childrenId = `project-${project.id}`
        return (
          <li key={project.id}>
            <div className={styles.treeRow}>
              <button
                type="button"
                className={styles.disclosure}
                aria-expanded={open}
                aria-controls={childrenId}
                onClick={() => toggle(project.id)}
              >
                <CaretRight size={11} weight="bold" aria-hidden="true" />
                <span className="visually-hidden">{project.name} 펼치기</span>
              </button>
              <NavLink to={paths.project(workspaceId, project.id)} className={styles.treeLink} end>
                <Cube aria-hidden="true" />
                <span className={styles.ellipsis}>{project.name}</span>
              </NavLink>
            </div>
            {open && (
              <ul id={childrenId} className={styles.treeChildren}>
                <li>
                  <NavLink to={paths.project(workspaceId, project.id)} end className={styles.navItem}>
                    <ListBullets aria-hidden="true" />
                    작업 목록
                  </NavLink>
                </li>
                <li>
                  <NavLink to={paths.assemblyTree(workspaceId, project.id)} className={styles.navItem}>
                    <TreeStructure aria-hidden="true" />
                    조립 트리
                  </NavLink>
                </li>
              </ul>
            )}
          </li>
        )
      })}
    </ul>
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
