"""2~5. 작업 생성, 이미지 해석, 작업자 확인, 결과 관리 (검색·승인·로봇 JSON) — /workspaces/{workspace_id}/jobs

작업은 프로젝트(블록)에 속하지만(project_id) 경로는 워크스페이스 하위다 — 워크스페이스 전체 검색 + ?project_id= 필터.
해석(analyze · review)은 VLM 호출로 수십 초 걸려서 요청은 바로 202 로 끝내고 백그라운드에서 돈다 — 그동안 작업 상태는
analyzing, 끝나면 결과 상태(needs_review · awaiting_approval), 실패하면 해석 전 상태 + analysis_error. GUI 는 작업을 다시 읽어 기다린다.
"""
import logging
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import BeforeValidator
from vision.image import load_image
from vw_shared import is_ref, latest_analysis, schema_errors

from app.api.deps import NOT_FOUND, StoreDep, WorkspaceDep, error_response
from app.export.robot_json import to_robot_json
from app.pipeline import (
    AnalysisError,
    analyze_image,
    job_with_analysis,
    manual_welding_condition,
    merge_corrections,
    review_analysis,
)
from app.schemas import AnalyzeRequest, ApproveRequest, Job, JobCreate, JobImage, JobStatus, ReviewRequest, RobotOutput
from app.store import JobStatusConflict, MissingForApproval, ReviewNotAcknowledged, Store

log = logging.getLogger(__name__)
router = APIRouter(responses=NOT_FOUND)  # 모든 경로가 워크스페이스(·작업) 하위 — 없으면 404

MAX_IMAGE_BYTES = 20 * 1024 * 1024
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


# ── 사진 · 해석 파이프라인 (app/pipeline.py: [1단계] vision → [2단계] db_context_interpreter → [3단계] calculate_reliability) ──

@router.post("/{job_id}/images", status_code=201, responses={
    413: error_response("파일이 너무 큼"), 422: error_response("이미지로 읽을 수 없음"),
})
async def upload_image(job: JobDep, file: UploadFile, store: StoreDep) -> JobImage:
    """사진 한 장 올리기 (multipart file). 해석은 POST .../analyze 로 따로 한다."""
    data = await file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, f"사진은 {MAX_IMAGE_BYTES // (1024 * 1024)}MB 까지 올릴 수 있습니다")
    try:
        height, width = load_image(data).shape[:2]
    except ValueError as e:
        raise HTTPException(422, "이미지로 읽을 수 없는 파일입니다") from e
    return store.add_image(job, file.filename or "photo", file.content_type or "application/octet-stream", data, width, height)


@router.get("/{job_id}/images")
def list_images(job: JobDep, store: StoreDep) -> list[JobImage]:
    """올린 순서 (가장 최근이 마지막)"""
    return store.list_images(job.id)


@router.get("/{job_id}/images/{image_id}/file", response_class=Response,
            responses={200: {"content": {"image/*": {}}, "description": "올린 사진 파일 그대로"}})
def image_file(image_id: str, job: JobDep, store: StoreDep) -> Response:
    found = store.get_image(job.id, image_id)
    if found is None:
        raise HTTPException(404, f"사진을 찾을 수 없습니다: {image_id}")
    image, data = found
    return Response(data, media_type=image.content_type)


@router.get("/{job_id}/images/{image_id}/preprocessed", response_class=Response,
            responses={200: {"content": {"image/png": {}}, "description": "1단계가 보정한 사진 (PNG)"}})
def preprocessed_file(image_id: str, job: JobDep, store: StoreDep) -> Response:
    """해석할 때 1단계가 보정한 사진 (작은 사진 키우기 · 노이즈 제거). 보정하지 않았거나 해석 전이면 404 (JobImage.preprocessed)"""
    data = store.get_preprocessed(image_id) if store.get_image(job.id, image_id) else None
    if data is None:
        raise HTTPException(404, f"보정한 사진이 없습니다: {image_id}")
    return Response(data, media_type="image/png")


@router.post("/{job_id}/analyze", status_code=202,
             responses={409: error_response("올린 사진이 없음 · 이미 해석 중")})
def analyze_job(job: JobDep, store: StoreDep, background: BackgroundTasks, body: AnalyzeRequest | None = None) -> Job:
    """사진 한 장을 1·2·3단계로 해석 (revision 1) → Analysis 저장, Job 에 반영. image_id 를 빼면 가장 최근 사진.
    바로 analyzing 상태의 작업을 돌려주고 백그라운드에서 해석한다."""
    images = store.list_images(job.id)
    if not images:
        raise HTTPException(409, "먼저 사진을 올려 주세요")
    image_id = body.image_id if body and body.image_id else images[-1].image_id
    found = store.get_image(job.id, image_id)
    if found is None:
        raise HTTPException(404, f"사진을 찾을 수 없습니다: {image_id}")
    started = _start(store, job)
    background.add_task(_run, store, job, lambda: analyze_image(store, job, load_image(found[1]), image_id))
    return started


@router.post("/{job_id}/review", status_code=202,
             responses={409: error_response("해석 결과가 없음 · 이미 해석 중"), 422: error_response("고친 값이 잘못됨")})
def review_job(job: JobDep, body: ReviewRequest, store: StoreDep, background: BackgroundTasks) -> Job:
    """작업자 확인 → 가장 최근 Analysis 에서 2단계부터 다시 해석 (revision + 1), Job 에 반영. analyze 처럼 백그라운드.

    reinterpret: context 를 맥락으로 덧붙임 / manual: values 의 키가 고칠 대상
    (t*·s*·v* · part · interpretation · welding_condition · cell · leg_lengths, shared/schemas/analysis.schema.json Correction).
    고친 값의 형식과 가리키는 표기는 바로 확인해 422 로 알려 준다.
    """
    analyses = store.list_analyses(job.id)
    if not analyses:
        raise HTTPException(409, "먼저 사진을 해석해 주세요")
    previous = latest_analysis(analyses)
    if body.action == "manual":
        values = dict(body.values or {})
        if not values:
            raise HTTPException(422, "고친 값이 없습니다")
        if isinstance(values.get("welding_condition"), dict):
            values["welding_condition"] = manual_welding_condition(values["welding_condition"], store.welding_standards)
        body = body.model_copy(update={"values": values})
        if errors := correction_errors(previous, values):
            raise HTTPException(422, f"고친 값을 반영할 수 없습니다: {'; '.join(errors)}")
    started = _start(store, job)
    background.add_task(_run, store, job, lambda: review_analysis(store, job, previous, body))
    return started


def correction_errors(previous: dict, values: dict) -> list[str]:
    """작업자가 고친 값이 Correction 형식에 맞는지, 가리키는 표기(t*·s*·v*)가 이전 해석에 있는지"""
    known = {d["id"] for d in previous["vision"]["texts"] + previous["vision"]["symbols"]}
    if vlm := previous["context"]["vlm"]:
        known |= {x["ref_id"] for x in vlm["reading"]["texts"] + vlm["reading"]["symbols"]}
    errors = []
    for correction in merge_corrections([], values.items(), previous):
        errors += [f"{correction['target']}: {e}" for e in schema_errors(correction, "analysis.schema.json#/$defs/Correction")]
        if is_ref(correction["target"]) and correction["target"] not in known:
            errors.append(f"{correction['target']}: 이전 해석에 없는 표기입니다")
    return errors


def _start(store: Store, job: Job) -> Job:
    try:
        started = store.start_analysis(job.workspace_id, job.id)
    except JobStatusConflict as e:
        raise HTTPException(409, "이미 해석 중입니다. 끝난 뒤에 다시 해 주세요") from e
    if started is None:
        raise HTTPException(404, f"작업을 찾을 수 없습니다: {job.id}")
    return started


def _run(store: Store, before: Job, interpret: Callable[[], dict]) -> None:
    """백그라운드 해석: 성공하면 Analysis 저장 + Job 반영, 실패하면 해석 전 상태(before)로 돌리고 이유를 남김"""
    try:
        analysis = interpret()
        updated = job_with_analysis(before, analysis)
    except AnalysisError as e:  # 단계 구현이 shared 스키마·규칙과 어긋남
        log.error("해석 결과가 공통 스키마와 맞지 않음 (%s): %s", before.id, e)
        store.finish_failed_analysis(before, f"해석 결과가 공통 스키마와 맞지 않습니다: {e}"[:1000])
        return
    except Exception as e:  # 모델 로드 · 이미지 · 단계 코드 오류
        log.exception("해석 실패 (%s)", before.id)
        store.finish_failed_analysis(before, f"해석 중 오류가 났습니다: {type(e).__name__}: {e}"[:1000])
        return
    store.add_analysis(before.id, analysis)
    store.save_job(_reanalyzed(updated))


@router.get("/{job_id}/analyses")
def list_analyses(job: JobDep, store: StoreDep) -> list[dict]:
    """해석 결과 (shared/schemas/analysis.schema.json) 전체, 만든 순서. 사진 위 bbox·후보를 그릴 때 쓴다."""
    return store.list_analyses(job.id)


def _reanalyzed(job: Job) -> Job:
    """다시 해석하면 이전 승인은 무효 (승인 대기·확인 필요로 돌아감)"""
    return job.model_copy(update={"approved_at": None, "approved_by": None})


# ── 승인 · 내보내기 ──

@router.post("/{job_id}/approve", responses={409: error_response("승인할 수 없는 상태 · 확인 항목 미확인 · 필수 값 없음")})
def approve_job(job: JobDep, body: ApproveRequest, store: StoreDep) -> Job:
    """승인 대기 작업은 바로, 확인 필요 작업은 acknowledge_review: true 일 때만 승인한다 (작업자가 확인 항목을 직접 봄).
    조립 경로 · 표기 · 용접 조건이 비어 있으면 로봇 JSON 을 만들 수 없어 승인하지 않는다."""
    # job 은 요청 시작 시점의 스냅샷 — 상태 확인은 저장소가 최신 상태로 다시 한다.
    try:
        approved = store.approve_job(job.workspace_id, job.id, body.approved_by, body.acknowledge_review)
    except JobStatusConflict as e:
        raise HTTPException(409, f"승인 대기·확인 필요 상태의 작업만 승인할 수 있습니다 (현재: {e.status})") from e
    except MissingForApproval as e:
        raise HTTPException(409, f"로봇 JSON 에 필요한 값이 비어 있어 승인할 수 없습니다: {', '.join(e.missing)}") from e
    except ReviewNotAcknowledged as e:
        raise HTTPException(409, f"확인 필요 항목 {len(e.needs_review)}개를 확인했다고 표시해야 승인할 수 있습니다 "
                                 "(acknowledge_review: true)") from e
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
