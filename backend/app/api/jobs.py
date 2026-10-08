"""2~5. 작업 생성, 이미지 해석, 작업자 확인, 결과 관리"""
from fastapi import APIRouter, UploadFile

router = APIRouter()


@router.post("")
def create_job():
    raise NotImplementedError


@router.post("/{job_id}/images")
async def upload_image(job_id: str, file: UploadFile):
    raise NotImplementedError


@router.post("/{job_id}/approve")
def approve_job(job_id: str):
    raise NotImplementedError


@router.get("/search")
def search_jobs(q: str):
    raise NotImplementedError


@router.get("/{job_id}/export")
def export_job(job_id: str):
    raise NotImplementedError
