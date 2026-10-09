from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

# 저장소 루트의 .env (API 키 · VLM_PROVIDER · CONFIDENCE_THRESHOLD). 이미 설정된 환경 변수가 우선
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from app.api import jobs, projects, standards, status, users, workspaces
from app.store import get_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_store()  # 시작 시 시드 로드 (인메모리 — 데모 사용자, 워크스페이스 "demo"·"personal", 표준 용접 기준)
    yield


app = FastAPI(title="Vision Welding AI", lifespan=lifespan)
app.include_router(users.router, tags=["users"])  # /me, /users
app.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])
app.include_router(projects.router, prefix="/workspaces/{workspace_id}/projects", tags=["projects"])
app.include_router(jobs.router, prefix="/workspaces/{workspace_id}/jobs", tags=["jobs"])
app.include_router(standards.router, prefix="/welding-standards", tags=["welding-standards"])
app.include_router(status.router, tags=["pipeline"])  # /pipeline/status


@app.get("/health")
def health():
    return {"status": "ok"}
