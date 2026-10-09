/** API 기본 경로. 기본값 '/api' 는 Vite 개발 서버가 백엔드로 프록시한다. */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/+$/, '')

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
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
  if (!res.ok) {
    throw new ApiError(res.status, `${res.status} ${res.statusText}`.trim())
  }
  const body = await res.text()
  return (body ? JSON.parse(body) : undefined) as T
}

export interface HealthResponse {
  status: string
}

/** GET /health — 백엔드 연결 확인 */
export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/health', { signal })
}
