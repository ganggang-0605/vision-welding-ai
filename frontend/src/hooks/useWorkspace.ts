import { useOutletContext } from 'react-router'
import type { Project, User, Workspace } from '../api/types'

/** WorkspaceLayout 이 <Outlet context> 로 내려주는 값 */
export interface WorkspaceOutletContext {
  workspace: Workspace
  /** 이 워크스페이스의 프로젝트(블록) 목록. 사이드바와 같은 값이다. */
  projects: Project[]
  /** 현재 사용자 (불러오기 전이면 undefined) */
  me: User | undefined
  /** 이름·종류·멤버 수를 바꾼 뒤 사이드바까지 다시 불러온다. */
  reloadWorkspace: () => void
  /** 프로젝트를 만든 뒤 사이드바 목록을 다시 불러온다. */
  reloadProjects: () => void
}

/** WorkspaceLayout 아래 페이지에서 쓰는 전체 컨텍스트 */
export function useWorkspaceContext(): WorkspaceOutletContext {
  return useOutletContext<WorkspaceOutletContext>()
}

/** 현재 워크스페이스. WorkspaceLayout 아래의 페이지에서만 쓴다 (불러오기가 끝난 뒤에 렌더된다). */
export function useWorkspace(): Workspace {
  return useWorkspaceContext().workspace
}
