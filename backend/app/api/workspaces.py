"""1. 워크스페이스 생성 및 문자/기호 체계 등록"""
from fastapi import APIRouter

router = APIRouter()


@router.post("")
def create_workspace():
    raise NotImplementedError


@router.post("/{workspace_id}/symbols")
def upsert_symbols(workspace_id: str):
    raise NotImplementedError
