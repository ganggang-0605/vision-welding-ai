/** 현재 사용자 API */
import { apiFetch } from './client'
import type { User } from './types'

/** GET /me — 로그인 기능이 생기기 전까지는 고정된 데모 사용자 (TODO 인증) */
export function getMe(signal?: AbortSignal): Promise<User> {
  return apiFetch<User>('/me', { signal })
}
