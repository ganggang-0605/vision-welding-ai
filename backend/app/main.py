from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import jobs, standards, workspaces
from app.store import get_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_store()  # 시작 시 시드 로드 (인메모리 — 데모 워크스페이스 "demo", 표준 용접 기준)
    yield


app = FastAPI(title="Vision Welding AI", lifespan=lifespan)
app.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])
app.include_router(jobs.router, prefix="/workspaces/{workspace_id}/jobs", tags=["jobs"])
app.include_router(standards.router, prefix="/welding-standards", tags=["welding-standards"])


@app.get("/health")
def health():
    return {"status": "ok"}
