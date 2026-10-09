"""1. 워크스페이스 생성 및 문자/기호 체계 등록 (+ 조립 트리)

TODO: 인증·멤버 관리 없음 — 지금은 누구나 모든 워크스페이스를 조회·수정할 수 있다.
"""
from fastapi import APIRouter, HTTPException

from app.api.deps import NOT_FOUND, StoreDep, WorkspaceDep, get_workspace
from app.schemas import (
    AssemblyNode,
    SymbolEntry,
    SymbolEntryCreate,
    SymbolEntryUpdate,
    Workspace,
    WorkspaceCreate,
)

router = APIRouter()


@router.get("")
def list_workspaces(store: StoreDep) -> list[Workspace]:
    return store.list_workspaces()


@router.post("", status_code=201, responses=NOT_FOUND)
def create_workspace(body: WorkspaceCreate, store: StoreDep) -> Workspace:
    """dictionary_source="copy" 면 copy_from_workspace_id 의 문자/기호 사전을 복제 (없는 워크스페이스면 404)"""
    copy_from = body.copy_from_workspace_id if body.dictionary_source == "copy" else None
    if copy_from:
        get_workspace(copy_from, store)
    return store.create_workspace(body.name, body.description, copy_symbols_from=copy_from)


@router.get("/{workspace_id}", responses=NOT_FOUND)
def read_workspace(workspace: WorkspaceDep) -> Workspace:
    return workspace


# ── 문자/기호 사전 ──

@router.get("/{workspace_id}/symbols", responses=NOT_FOUND)
def list_symbols(workspace: WorkspaceDep, store: StoreDep) -> list[SymbolEntry]:
    return store.list_symbols(workspace.id)


@router.post("/{workspace_id}/symbols", status_code=201, responses=NOT_FOUND)
def create_symbol(body: SymbolEntryCreate, workspace: WorkspaceDep, store: StoreDep) -> SymbolEntry:
    return store.create_symbol(workspace.id, body)


@router.patch("/{workspace_id}/symbols/{symbol_id}", responses=NOT_FOUND)
def update_symbol(
    symbol_id: str, body: SymbolEntryUpdate, workspace: WorkspaceDep, store: StoreDep
) -> SymbolEntry:
    updated = store.update_symbol(workspace.id, symbol_id, body.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(404, f"문자/기호를 찾을 수 없습니다: {symbol_id}")
    return updated


@router.delete("/{workspace_id}/symbols/{symbol_id}", status_code=204, responses=NOT_FOUND)
def delete_symbol(symbol_id: str, workspace: WorkspaceDep, store: StoreDep) -> None:
    if not store.delete_symbol(workspace.id, symbol_id):
        raise HTTPException(404, f"문자/기호를 찾을 수 없습니다: {symbol_id}")


# ── 조립 트리 ──

@router.get("/{workspace_id}/assembly-tree", responses=NOT_FOUND)
def get_assembly_tree(workspace: WorkspaceDep, store: StoreDep) -> list[AssemblyNode]:
    return store.get_assembly_tree(workspace.id)
