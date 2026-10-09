import { useOutletContext } from 'react-router'
import type { Project } from '../api/types'
import type { WorkspaceOutletContext } from './useWorkspace'

/** ProjectLayout 이 워크스페이스 컨텍스트에 현재 프로젝트를 더해 내려준다. */
export interface ProjectOutletContext extends WorkspaceOutletContext {
  project: Project
}

/** 현재 프로젝트(호선). ProjectLayout(/w/:workspaceId/p/:projectId) 아래 페이지에서만 쓴다. */
export function useProject(): Project {
  return useOutletContext<ProjectOutletContext>().project
}
