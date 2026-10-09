"""1. 워크스페이스 생성·수정, 멤버 초대, 문자/기호 체계 등록

워크스페이스는 개인(personal) 또는 팀(team). 개인 워크스페이스에 멤버를 초대하면 팀으로 바뀐다.
프로젝트(블록)·조립 트리는 api/projects.py, 작업은 api/jobs.py.
TODO(인증): 로그인 없음 — X-User-Id 헤더(없으면 데모 사용자)가 현재 사용자다. 목록(GET /workspaces)만 멤버로 거르고,
TODO(권한): 그 밖의 경로는 권한 검사 없이 누구나 모든 워크스페이스를 조회·수정할 수 있다.
"""
from fastapi import APIRouter, HTTPException

from app.api.deps import (
    NOT_FOUND,
    UNKNOWN_USER,
    CurrentUserDep,
    StoreDep,
    WorkspaceDep,
    error_response,
    get_workspace,
)
from app.schemas import (
    Member,
    MemberInvite,
    SymbolEntry,
    SymbolEntryCreate,
    SymbolEntryUpdate,
    Workspace,
    WorkspaceCreate,
    WorkspaceUpdate,
)
from app.store import MemberAlreadyExists, WorkspaceKindConflict

router = APIRouter()


@router.get("", responses=UNKNOWN_USER)
def list_workspaces(store: StoreDep, user: CurrentUserDep) -> list[Workspace]:
    """현재 사용자(X-User-Id)가 멤버인 워크스페이스만 — 시드(폴더 이름순) 다음에 새로 만든 워크스페이스가 생성 순.

    TODO(권한): 목록만 거른다. 다른 워크스페이스 경로는 id 만 알면 누구나 접근할 수 있다.
    """
    return store.list_workspaces(member_id=user.id)


@router.post("", status_code=201, responses={**NOT_FOUND, **UNKNOWN_USER})
def create_workspace(body: WorkspaceCreate, store: StoreDep, user: CurrentUserDep) -> Workspace:
    """현재 사용자(X-User-Id)가 소유자(owner) 멤버가 된다 (kind 기본값 "personal").

    dictionary_source="copy" 면 copy_from_workspace_id 의 문자/기호 사전을 복제 (없는 워크스페이스면 404)
    """
    copy_from = body.copy_from_workspace_id if body.dictionary_source == "copy" else None
    if copy_from:
        get_workspace(copy_from, store)
    return store.create_workspace(
        body.name, owner=user, description=body.description, kind=body.kind, copy_symbols_from=copy_from
    )


@router.get("/{workspace_id}", responses=NOT_FOUND)
def read_workspace(workspace: WorkspaceDep) -> Workspace:
    return workspace


@router.patch(
    "/{workspace_id}", responses={**NOT_FOUND, 409: error_response("멤버가 여럿인 워크스페이스를 개인으로 전환")}
)
def update_workspace(body: WorkspaceUpdate, workspace: WorkspaceDep, store: StoreDep) -> Workspace:
    """부분 수정. team → personal 은 멤버가 1명(소유자)일 때만 (아니면 409)."""
    try:
        updated = store.update_workspace(workspace.id, body.model_dump(exclude_unset=True))
    except WorkspaceKindConflict as e:
        raise HTTPException(
            409, f"멤버가 1명일 때만 개인 워크스페이스로 바꿀 수 있습니다 (현재 멤버: {e.member_count}명)"
        ) from e
    if updated is None:
        raise HTTPException(404, f"워크스페이스를 찾을 수 없습니다: {workspace.id}")
    return updated


# ── 멤버 ──

@router.get("/{workspace_id}/members", responses=NOT_FOUND)
def list_members(workspace: WorkspaceDep, store: StoreDep) -> list[Member]:
    """소유자 먼저, 그다음 가입 순"""
    return store.list_members(workspace.id)


@router.post(
    "/{workspace_id}/members", status_code=201, responses={**NOT_FOUND, 409: error_response("이미 멤버인 이메일")}
)
def invite_member(body: MemberInvite, workspace: WorkspaceDep, store: StoreDep) -> Member:
    """이메일로 멤버 초대 (role "member"). 같은 이메일(대소문자 무시)의 사용자가 있으면 그 사용자를 초대한다
    (이름은 기존 사용자 이름 유지). 개인 워크스페이스는 팀 워크스페이스로 바뀐다.
    """
    try:
        return store.invite_member(workspace.id, body.name, body.email)
    except MemberAlreadyExists as e:
        raise HTTPException(409, f"이미 이 워크스페이스의 멤버입니다: {e.email}") from e


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
