/** 작업 API — 모두 워크스페이스 안에서만 조회·처리한다. */
import { apiFetch, apiPath, jsonInit } from './client'
import type { ApproveRequest, Job, JobCreate, JobListParams, ReviewRequest, RobotOutput } from './types'

/** GET /workspaces/{workspace_id}/jobs?q=&status= (최신순) */
export function listJobs(workspaceId: string, params: JobListParams = {}, signal?: AbortSignal): Promise<Job[]> {
  const query = new URLSearchParams()
  if (params.q) query.set('q', params.q)
  if (params.status) query.set('status', params.status)
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
 * POST /workspaces/{workspace_id}/jobs/{job_id}/images (multipart "file")
 * Content-Type 은 브라우저가 boundary 와 함께 붙이도록 직접 지정하지 않는다.
 * 파이프라인 구현 전까지 501.
 */
export function uploadJobImage(workspaceId: string, jobId: string, file: File, signal?: AbortSignal): Promise<Job> {
  const form = new FormData()
  form.append('file', file)
  return apiFetch<Job>(apiPath`/workspaces/${workspaceId}/jobs/${jobId}/images`, {
    method: 'POST',
    body: form,
    signal,
  })
}

/** POST /workspaces/{workspace_id}/jobs/{job_id}/analyze — 파이프라인 구현 전까지 501 */
export function analyzeJob(workspaceId: string, jobId: string, signal?: AbortSignal): Promise<Job> {
  return apiFetch<Job>(apiPath`/workspaces/${workspaceId}/jobs/${jobId}/analyze`, { method: 'POST', signal })
}

/** POST /workspaces/{workspace_id}/jobs/{job_id}/review — 파이프라인 구현 전까지 501 */
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
