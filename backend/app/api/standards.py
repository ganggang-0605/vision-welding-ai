"""표준 용접 기준 DB — 모든 워크스페이스가 공유하는 공식 기준 (읽기 전용)"""
from fastapi import APIRouter

from app.api.deps import StoreDep
from app.schemas import WeldingStandard

router = APIRouter()


@router.get("")
def list_welding_standards(store: StoreDep) -> list[WeldingStandard]:
    return store.welding_standards
