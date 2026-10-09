/** 작업 API — 모두 워크스페이스 안에서만 조회·처리한다. */
import { API_BASE_URL, apiFetch, apiPath, jsonInit } from './client'
import type {
  Analysis,
  AnalyzeRequest,
  ApproveRequest,
  Job,
  JobCreate,
  JobImage,
  JobListParams,
  ReviewRequest,
  RobotOutput,
} from './types'

/** GET /workspaces/{workspace_id}/jobs?q=&status=&project_id= (최신순) */
export function listJobs(workspaceId: string, params: JobListParams = {}, signal?: AbortSignal): Promise<Job[]> {
  const query = new URLSearchParams()
  if (params.q) query.set('q', params.q)
  if (params.status) query.set('status', params.status)
  if (params.project_id) query.set('project_id', params.project_id)
  const qs = query.toString()
  return apiFetch<Job[]>(apiPath`/workspaces/${workspaceId}/jobs` + (qs ? `?${qs}` : ''), { signal })
}

/** POST /workspaces/{workspace_id}/jobs → 201 (status "draft") */
export function createJob(workspaceId: string, body: JobCreate, signal?: AbortSignal): Promise<Job> {
  return apiFetch<Job>(apiPath`/workspaces/${workspaceId}/jobs`, jsonInit('POST', body, signal))
}

/** GET /workspaces/{workspace_id}/jobs/{job_id} (다른 워크스페이스의 작업이면 404) */
export function getJob(workspaceId: string, jobId: string, signal?: AbortSignal): Promise<Job> {
  return apiFetch<Job>(apiPath`/workspaces/${workspaceId}/jobs/${jobId}`, { signal })
}

/**
 * POST /workspaces/{workspace_id}/jobs/{job_id}/images (multipart "file") → 201.
 * Content-Type 은 브라우저가 boundary 와 함께 붙이도록 직접 지정하지 않는다. 20MB 초과 413, 이미지가 아니면 422.
 */
export function uploadJobImage(workspaceId: string, jobId: string, file: File, signal?: AbortSignal): Promise<JobImage> {
  const form = new FormData()
  form.append('file', file)
  return apiFetch<JobImage>(apiPath`/workspaces/${workspaceId}/jobs/${jobId}/images`, {
    method: 'POST',
    body: form,
    signal,
  })
}

/** GET /workspaces/{workspace_id}/jobs/{job_id}/images (올린 순서, 가장 최근이 마지막) */
export function listJobImages(workspaceId: string, jobId: string, signal?: AbortSignal): Promise<JobImage[]> {
  return apiFetch<JobImage[]>(apiPath`/workspaces/${workspaceId}/jobs/${jobId}/images`, { signal })
}

/** <img src> 에 바로 쓰는 사진 파일 주소 */
export function jobImageUrl(workspaceId: string, jobId: string, imageId: string): string {
  return API_BASE_URL + apiPath`/workspaces/${workspaceId}/jobs/${jobId}/images/${imageId}/file`
}

/** POST /workspaces/{workspace_id}/jobs/{job_id}/analyze — 1·2·3단계 해석 후 반영된 작업. 사진이 없으면 409 */
export function analyzeJob(workspaceId: string, jobId: string, body: AnalyzeRequest = {}, signal?: AbortSignal): Promise<Job> {
  return apiFetch<Job>(apiPath`/workspaces/${workspaceId}/jobs/${jobId}/analyze`, jsonInit('POST', body, signal))
}

/** GET /workspaces/{workspace_id}/jobs/{job_id}/analyses — 해석 결과 전체 (만든 순서) */
export function listAnalyses(workspaceId: string, jobId: string, signal?: AbortSignal): Promise<Analysis[]> {
  return apiFetch<Analysis[]>(apiPath`/workspaces/${workspaceId}/jobs/${jobId}/analyses`, { signal })
}

/** POST /workspaces/{workspace_id}/jobs/{job_id}/review — 2단계부터 다시 해석. 해석 전이면 409, 잘못된 값이면 422 */
export function reviewJob(
  workspaceId: string,
  jobId: string,
  body: ReviewRequest,
  signal?: AbortSignal,
): Promise<Job> {
  return apiFetch<Job>(apiPath`/workspaces/${workspaceId}/jobs/${jobId}/review`, jsonInit('POST', body, signal))
}

/** POST /workspaces/{workspace_id}/jobs/{job_id}/approve (needs_review·awaiting_approval 이 아니면 409) */
export function approveJob(
  workspaceId: string,
  jobId: string,
  body: ApproveRequest,
  signal?: AbortSignal,
): Promise<Job> {
  return apiFetch<Job>(apiPath`/workspaces/${workspaceId}/jobs/${jobId}/approve`, jsonInit('POST', body, signal))
}

/** GET /workspaces/{workspace_id}/jobs/{job_id}/export — 로봇 연계 JSON (승인 전이면 409) */
export function exportJob(workspaceId: string, jobId: string, signal?: AbortSignal): Promise<RobotOutput> {
  return apiFetch<RobotOutput>(apiPath`/workspaces/${workspaceId}/jobs/${jobId}/export`, { signal })
}
