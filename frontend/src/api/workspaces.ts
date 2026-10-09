/** 워크스페이스, 워크스페이스별 문자/기호 사전·조립 트리 API */
import { apiFetch, apiPath, jsonInit } from './client'
import type {
  AssemblyNode,
  SymbolEntry,
  SymbolEntryCreate,
  SymbolEntryUpdate,
  Workspace,
  WorkspaceCreate,
} from './types'

// TODO(인증): 로그인·멤버 기능이 생기면 내가 속한 워크스페이스만 내려오도록 바뀐다.

/** GET /workspaces */
export function listWorkspaces(signal?: AbortSignal): Promise<Workspace[]> {
  return apiFetch<Workspace[]>('/workspaces', { signal })
}

/** POST /workspaces → 201. copy 인데 원본이 없으면 404, id 가 빠지면 422 */
export function createWorkspace(body: WorkspaceCreate, signal?: AbortSignal): Promise<Workspace> {
  return apiFetch<Workspace>('/workspaces', jsonInit('POST', body, signal))
}

/** GET /workspaces/{workspace_id} (없으면 404) */
export function getWorkspace(workspaceId: string, signal?: AbortSignal): Promise<Workspace> {
  return apiFetch<Workspace>(apiPath`/workspaces/${workspaceId}`, { signal })
}

/** GET /workspaces/{workspace_id}/symbols */
export function listSymbols(workspaceId: string, signal?: AbortSignal): Promise<SymbolEntry[]> {
  return apiFetch<SymbolEntry[]>(apiPath`/workspaces/${workspaceId}/symbols`, { signal })
}

/** POST /workspaces/{workspace_id}/symbols → 201 */
export function createSymbol(
  workspaceId: string,
  body: SymbolEntryCreate,
  signal?: AbortSignal,
): Promise<SymbolEntry> {
  return apiFetch<SymbolEntry>(apiPath`/workspaces/${workspaceId}/symbols`, jsonInit('POST', body, signal))
}

/** PATCH /workspaces/{workspace_id}/symbols/{symbol_id} */
export function updateSymbol(
  workspaceId: string,
  symbolId: string,
  body: SymbolEntryUpdate,
  signal?: AbortSignal,
): Promise<SymbolEntry> {
  return apiFetch<SymbolEntry>(
    apiPath`/workspaces/${workspaceId}/symbols/${symbolId}`,
    jsonInit('PATCH', body, signal),
  )
}

/** DELETE /workspaces/{workspace_id}/symbols/{symbol_id} → 204 */
export function deleteSymbol(workspaceId: string, symbolId: string, signal?: AbortSignal): Promise<void> {
  return apiFetch<void>(apiPath`/workspaces/${workspaceId}/symbols/${symbolId}`, { method: 'DELETE', signal })
}

/** GET /workspaces/{workspace_id}/assembly-tree */
export function getAssemblyTree(workspaceId: string, signal?: AbortSignal): Promise<AssemblyNode[]> {
  return apiFetch<AssemblyNode[]>(apiPath`/workspaces/${workspaceId}/assembly-tree`, { signal })
}
