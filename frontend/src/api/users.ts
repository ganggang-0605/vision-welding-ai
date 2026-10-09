/** 사용자 API (로그인 전 데모 계정) */
import { apiFetch, asUser } from './client'
import type { User } from './types'

/** GET /users — '계정 추가하기'에서 고를 데모 계정 목록. 로그인 기능이 생기면 없어진다 (TODO 인증). */
export function listUsers(signal?: AbortSignal): Promise<User[]> {
  return apiFetch<User[]>('/users', { signal })
}

/** GET /me — 지금 계정(X-User-Id)의 사용자. userId 를 주면 그 계정으로 묻는다 (TODO 인증) */
export function getMe(signal?: AbortSignal, userId?: string): Promise<User> {
  return apiFetch<User>('/me', userId ? asUser(userId, { signal }) : { signal })
}
