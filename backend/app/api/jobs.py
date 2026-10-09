"""2~5. 작업 생성, 이미지 해석, 작업자 확인, 결과 관리 (검색·승인·로봇 JSON) — /workspaces/{workspace_id}/jobs

작업은 프로젝트(호선)에 속하지만(project_id) 경로는 워크스페이스 하위다 — 워크스페이스 전체 검색 + ?project_id= 필터.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import BeforeValidator

from app.api.deps import NOT_FOUND, StoreDep, WorkspaceDep, error_response
from app.export.robot_json import to_robot_json
from app.schemas import ApproveRequest, Job, JobCreate, JobStatus, ReviewRequest, RobotOutput
from app.store import JobStatusConflict

router = APIRouter(responses=NOT_FOUND)  # 모든 경로가 워크스페이스(·작업) 하위 — 없으면 404

NOT_IMPLEMENTED = {501: error_response("해석 파이프라인 미구현")}
# ?status= · ?project_id= 처럼 빈 값이면 필터 없음 (q 와 같게)
StatusFilter = Annotated[JobStatus | None, BeforeValidator(lambda v: v or None)]
ProjectFilter = Annotated[str | None, BeforeValidator(lambda v: v or None)]


def get_job(job_id: str, workspace: WorkspaceDep, store: StoreDep) -> Job:
    """해당 워크스페이스의 작업만 찾는다 — 다른 워크스페이스의 작업 id 면 404."""
    job = store.get_job(workspace.id, job_id)
    if job is None:
        raise HTTPException(404, f"작업을 찾을 수 없습니다: {job_id}")
    return job


JobDep = Annotated[Job, Depends(get_job)]


@router.get("")
def list_jobs(
    workspace: WorkspaceDep,
    store: StoreDep,
    q: str | None = None,
    status: StatusFilter = None,
    project_id: ProjectFilter = None,
) -> list[Job]:
    """작업 DB 검색 — q: 이름·조립 경로·표기 원문/해석 (대소문자 무시), status: 상태 필터,
    project_id: 프로젝트 필터 (빈 값이면 전체, 없는 id 면 빈 목록). 최신순."""
    return store.list_jobs(workspace.id, q=q, status=status, project_id=project_id)


@router.post("", status_code=201)
def create_job(body: JobCreate, workspace: WorkspaceDep, store: StoreDep) -> Job:
    """project_id 는 같은 워크스페이스의 프로젝트, related_job_ids 는 같은 워크스페이스에 있는 작업만 (아니면 422)"""
    errors = []
    if store.get_project(workspace.id, body.project_id) is None:
        errors.append({"type": "value_error", "loc": ("body", "project_id"), "input": body.project_id,
                       "msg": f"같은 워크스페이스에 없는 프로젝트입니다: {body.project_id}"})
    errors += [
        {"type": "value_error", "loc": ("body", "related_job_ids", i), "input": job_id,
         "msg": f"같은 워크스페이스에 없는 작업입니다: {job_id}"}
        for i, job_id in enumerate(body.related_job_ids)
        if store.get_job(workspace.id, job_id) is None
    ]
    if errors:
        raise RequestValidationError(errors)
    return store.create_job(workspace.id, body)


@router.get("/{job_id}")
def read_job(job: JobDep) -> Job:
    return job


# ── 해석 파이프라인 (미구현 → 501) ──

@router.post("/{job_id}/images", responses=NOT_IMPLEMENTED)
def upload_image(job: JobDep, file: UploadFile) -> Job:
    raise HTTPException(501, "이미지 업로드는 아직 구현되지 않았습니다 (해석 파이프라인 연동 예정)")


@router.post("/{job_id}/analyze", responses=NOT_IMPLEMENTED)
def analyze_job(job: JobDep) -> Job:
    raise HTTPException(501, "표기 정보 해석은 아직 구현되지 않았습니다 (해석 파이프라인 연동 예정)")


@router.post("/{job_id}/review", responses=NOT_IMPLEMENTED)
def review_job(job: JobDep, body: ReviewRequest) -> Job:
    raise HTTPException(501, "재해석·직접 해석은 아직 구현되지 않았습니다 (해석 파이프라인 연동 예정)")


# ── 승인 · 내보내기 ──

@router.post("/{job_id}/approve", responses={409: error_response("승인할 수 없는 상태")})
def approve_job(job: JobDep, body: ApproveRequest, store: StoreDep) -> Job:
    # job 은 요청 시작 시점의 스냅샷 — 상태 확인은 저장소가 최신 상태로 다시 한다.
    try:
        approved = store.approve_job(job.workspace_id, job.id, body.approved_by)
    except JobStatusConflict as e:
        raise HTTPException(409, f"승인 대기·검토 필요 상태의 작업만 승인할 수 있습니다 (현재: {e.status})") from e
    if approved is None:
        raise HTTPException(404, f"작업을 찾을 수 없습니다: {job.id}")
    return approved


@router.get("/{job_id}/export", response_model=RobotOutput, responses={409: error_response("승인되지 않은 작업")})
def export_job(job: JobDep) -> dict:
    """승인된 작업 → 로봇 연계용 JSON (shared/schemas/robot_output.schema.json)"""
    try:
        return to_robot_json(job)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
