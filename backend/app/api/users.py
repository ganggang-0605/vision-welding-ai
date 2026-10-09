"""현재 사용자 — /me

TODO(인증): 로그인 없음 — 시드의 고정 데모 사용자를 돌려준다.
"""
from fastapi import APIRouter

from app.api.deps import CurrentUserDep
from app.schemas import User

router = APIRouter()


@router.get("")
def read_me(user: CurrentUserDep) -> User:
    return user
