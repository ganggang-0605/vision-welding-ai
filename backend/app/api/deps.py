"""라우터 공통 의존성"""
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from app.schemas import ErrorDetail, User, Workspace
from app.store import Store, get_store

StoreDep = Annotated[Store, Depends(get_store)]


def error_response(description: str) -> dict:
    """OpenAPI 의 오류 응답 항목 — 본문은 {"detail": "..."}"""
    return {"model": ErrorDetail, "description": description}


NOT_FOUND = {404: error_response("워크스페이스·프로젝트·작업·항목을 찾을 수 없음")}
UNKNOWN_USER = {401: error_response("X-User-Id 헤더의 사용자를 찾을 수 없음")}


def get_current_user(
    store: StoreDep, x_user_id: Annotated[str | None, Header(description="데모 사용자 id (인증 전 임시)")] = None
) -> User:
    """현재 사용자 (Notion 식 데모 다중 계정).

    TODO(인증): X-User-Id 헤더가 로그인 세션을 대신한다 — 없거나 빈 값이면 시드의 current_user_id(데모 사용자),
    모르는 id 면 401. 실제 인증을 붙이면 세션·토큰에서 사용자를 꺼내도록 이 함수만 바꾼다.
    """
    if not x_user_id:
        return store.default_user()
    user = store.get_user(x_user_id)
    if user is None:
        raise HTTPException(401, f"알 수 없는 사용자입니다: {x_user_id}")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def get_workspace(workspace_id: str, store: StoreDep) -> Workspace:
    """경로의 workspace_id 확인 — 워크스페이스 하위 라우트 공통. 없으면 404."""
    workspace = store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(404, f"워크스페이스를 찾을 수 없습니다: {workspace_id}")
    return workspace


WorkspaceDep = Annotated[Workspace, Depends(get_workspace)]
