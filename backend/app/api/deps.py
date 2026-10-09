"""라우터 공통 의존성"""
from typing import Annotated

from fastapi import Depends, HTTPException

from app.schemas import ErrorDetail, User, Workspace
from app.store import Store, get_store

StoreDep = Annotated[Store, Depends(get_store)]


def error_response(description: str) -> dict:
    """OpenAPI 의 오류 응답 항목 — 본문은 {"detail": "..."}"""
    return {"model": ErrorDetail, "description": description}


NOT_FOUND = {404: error_response("워크스페이스·프로젝트·작업·항목을 찾을 수 없음")}


def get_current_user(store: StoreDep) -> User:
    """현재 사용자. TODO(인증): 로그인 전까지는 시드의 고정 데모 사용자 (data/seed/users.json 의 current_user_id)."""
    return store.current_user()


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def get_workspace(workspace_id: str, store: StoreDep) -> Workspace:
    """경로의 workspace_id 확인 — 워크스페이스 하위 라우트 공통. 없으면 404."""
    workspace = store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(404, f"워크스페이스를 찾을 수 없습니다: {workspace_id}")
    return workspace


WorkspaceDep = Annotated[Workspace, Depends(get_workspace)]
