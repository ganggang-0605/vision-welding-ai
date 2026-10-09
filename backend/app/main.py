import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

# 저장소 루트의 .env (API 키 · VLM_PROVIDER · CONFIDENCE_THRESHOLD). 이미 설정된 환경 변수가 우선
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from app.api import jobs, projects, standards, status, users, workspaces
from app.db.connect import describe
from app.store import get_store


log = logging.getLogger(__name__)


def _warm_up_models() -> None:
    """[1단계] OCR 모델을 미리 불러 둠 (첫 해석이 모델 로드로 1분 가까이 걸리지 않게). 실패해도 해석 때 다시 시도"""
    from vision.ocr import warm_up

    try:
        if warm_up():
            log.info("OCR 모델을 미리 불러 둠")
    except Exception:
        log.exception("OCR 모델을 미리 불러오지 못함 (첫 해석 때 다시 불러옴)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시 저장소 로드 — DATABASE_URL 의 DB(PostgreSQL · SQLite, 비어 있으면 시드: 데모 사용자, 워크스페이스 "demo"·"personal")
    get_store()
    log.info("저장소: %s", describe(os.environ.get("DATABASE_URL")))
    if os.environ.get("PRELOAD_MODELS", "1") != "0":
        threading.Thread(target=_warm_up_models, name="warm-up-models", daemon=True).start()
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
