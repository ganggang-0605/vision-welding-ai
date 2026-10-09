/** 프로젝트(호선) API. 조립 트리는 프로젝트마다 따로 있다. */
import { apiFetch, apiPath, jsonInit } from './client'
import type { AssemblyNode, Project, ProjectCreate } from './types'

/** GET /workspaces/{workspace_id}/projects (만든 순서) */
export function listProjects(workspaceId: string, signal?: AbortSignal): Promise<Project[]> {
  return apiFetch<Project[]>(apiPath`/workspaces/${workspaceId}/projects`, { signal })
}

/** POST /workspaces/{workspace_id}/projects → 201 (조립 트리는 비어 있다) */
export function createProject(workspaceId: string, body: ProjectCreate, signal?: AbortSignal): Promise<Project> {
  return apiFetch<Project>(apiPath`/workspaces/${workspaceId}/projects`, jsonInit('POST', body, signal))
}

/** GET /workspaces/{workspace_id}/projects/{project_id} (다른 워크스페이스의 프로젝트면 404) */
export function getProject(workspaceId: string, projectId: string, signal?: AbortSignal): Promise<Project> {
  return apiFetch<Project>(apiPath`/workspaces/${workspaceId}/projects/${projectId}`, { signal })
}

/** GET /workspaces/{workspace_id}/projects/{project_id}/assembly-tree */
export function getAssemblyTree(workspaceId: string, projectId: string, signal?: AbortSignal): Promise<AssemblyNode[]> {
  return apiFetch<AssemblyNode[]>(apiPath`/workspaces/${workspaceId}/projects/${projectId}/assembly-tree`, { signal })
}
