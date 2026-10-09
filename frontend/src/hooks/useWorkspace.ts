import { useOutletContext } from 'react-router'
import type { Workspace } from '../api/types'

/** WorkspaceLayout 이 <Outlet context> 로 내려주는 값 */
export interface WorkspaceOutletContext {
  workspace: Workspace
}

/** 현재 워크스페이스. WorkspaceLayout 아래의 페이지에서만 쓴다 (불러오기가 끝난 뒤에 렌더된다). */
export function useWorkspace(): Workspace {
  return useOutletContext<WorkspaceOutletContext>().workspace
}
