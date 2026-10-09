/** API 기본 경로. 기본값 '/api' 는 Vite 개발 서버가 백엔드로 프록시한다. */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/+$/, '')

export class ApiError extends Error {
  readonly status: number
  /** FastAPI 오류 본문의 `detail` (문자열이면 그대로, 422 검증 오류 등은 원본 값) */
  readonly detail: unknown

  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

/** 특정 HTTP 상태 코드의 ApiError 인지 확인한다. 예: `isApiError(err, 501)` */
export function isApiError(error: unknown, status?: number): error is ApiError {
  return error instanceof ApiError && (status === undefined || error.status === status)
}

/**
 * JSON 응답을 T 타입으로 받는 fetch 래퍼. 2xx 가 아니면 ApiError 를 던진다.
 * 204 No Content 처럼 본문이 비어 있으면 undefined 를 돌려준다 (`apiFetch<void>(...)`).
 */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
  const headers = new Headers(init?.headers)
  if (!headers.has('Accept')) headers.set('Accept', 'application/json')

  const res = await fetch(url, { ...init, headers })
  const body = await res.text()
  if (!res.ok) {
    const detail = parseDetail(body)
    const message = typeof detail === 'string' ? detail : `${res.status} ${res.statusText}`.trim()
    throw new ApiError(res.status, message, detail)
  }
  return (body ? JSON.parse(body) : undefined) as T
}

/** FastAPI 오류 본문 `{"detail": ...}` 에서 detail 을 꺼낸다. JSON 이 아니면 undefined. */
function parseDetail(body: string): unknown {
  try {
    const parsed: unknown = JSON.parse(body)
    return parsed && typeof parsed === 'object' && 'detail' in parsed ? parsed.detail : undefined
  } catch {
    return undefined
  }
}

/** JSON 본문을 보내는 요청의 RequestInit */
export function jsonInit(method: 'POST' | 'PATCH' | 'PUT', body: unknown, signal?: AbortSignal): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  }
}

/**
 * 경로 파라미터를 encodeURIComponent 로 인코딩하는 템플릿 태그.
 * 예: apiPath`/workspaces/${workspaceId}/jobs/${jobId}`
 */
export function apiPath(strings: TemplateStringsArray, ...params: string[]): string {
  return strings.reduce((acc, part, i) => acc + part + (i < params.length ? encodeURIComponent(params[i]) : ''), '')
}

export interface HealthResponse {
  status: string
}

/** GET /health — 백엔드 연결 확인 */
export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/health', { signal })
}
