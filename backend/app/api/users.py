"""사용자 — /me (현재 사용자), /users (데모 계정 목록)

TODO(인증): 로그인 없음 — 요청 헤더 X-User-Id 가 로그인 세션을 대신해 현재 사용자를 고른다 (없으면 데모 사용자).
"""
from fastapi import APIRouter

from app.api.deps import UNKNOWN_USER, CurrentUserDep, StoreDep
from app.schemas import User

router = APIRouter()


@router.get("/me", responses=UNKNOWN_USER)
def read_me(user: CurrentUserDep) -> User:
    """X-User-Id 헤더의 사용자 (없으면 데모 사용자, 모르는 id 면 401)"""
    return user


@router.get("/users")
def list_users(store: StoreDep) -> list[User]:
    """모든 데모 사용자 (시드 순) — 프론트엔드의 "계정 추가하기"에서 고를 목록.

    TODO(인증): 로그인이 없어서 있는 임시 API — 실제 인증을 붙이면 없앤다.
    """
    return store.list_users()
