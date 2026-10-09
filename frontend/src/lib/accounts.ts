/**
 * 로그인한 데모 계정 목록과 지금 쓰는 계정 (노션의 '계정 추가하기' 흉내).
 * 로그인 기능이 생기기 전까지 비밀번호 없이 데모 사용자를 고르고, API 요청에 X-User-Id 헤더로 붙인다.
 * 이 브라우저에만 저장한다. TODO(인증): 실제 로그인 세션으로 바꾸면 이 모듈을 세션 정보로 대체한다.
 */
import { useSyncExternalStore } from 'react'

/** 처음 열었을 때 자동으로 로그인되는 데모 계정 (백엔드 시드의 current_user_id) */
export const DEFAULT_ACCOUNT_ID = 'user_kkm'

/** 예전 시드 계정 id → 지금 id (팀원 이름으로 바꾸기 전에 이 브라우저에 저장된 계정을 이어 쓰게) */
const RENAMED_IDS: Record<string, string> = { user_demo: 'user_kkm', user_park: 'user_ldh', user_choi: 'user_lmh' }

const STORAGE_KEY = 'vwa:accounts'

export interface AccountState {
  /** 로그인한 계정 id (추가한 순서) */
  accountIds: readonly string[]
  /** 지금 쓰는 계정. 로그인한 계정이 없으면 undefined */
  activeId: string | undefined
}

const listeners = new Set<() => void>()
let state: AccountState = load()

function load(): AccountState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<AccountState>
      const rename = (id: string) => RENAMED_IDS[id] ?? id
      const stored = Array.isArray(parsed.accountIds) ? parsed.accountIds.filter((id) => typeof id === 'string') : []
      const accountIds = [...new Set(stored.map(rename))]
      const active = typeof parsed.activeId === 'string' ? rename(parsed.activeId) : undefined
      const activeId = active && accountIds.includes(active) ? active : accountIds[0]
      return { accountIds, activeId }
    }
  } catch {
    // 저장소를 못 쓰거나 값이 깨졌으면 기본 계정으로 시작한다.
  }
  return { accountIds: [DEFAULT_ACCOUNT_ID], activeId: DEFAULT_ACCOUNT_ID }
}

function save(next: AccountState): void {
  state = next
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    // 이번 방문 동안만 유지된다.
  }
  listeners.forEach((listener) => listener())
}

/** API 클라이언트가 요청마다 읽는다 (React 밖). */
export function getActiveAccountId(): string | undefined {
  return state.activeId
}

/** 계정을 추가하고(이미 있으면 그대로) 그 계정으로 바꾼다. */
export function signIn(userId: string): void {
  const accountIds = state.accountIds.includes(userId) ? state.accountIds : [...state.accountIds, userId]
  save({ accountIds, activeId: userId })
}

/** 이미 로그인한 계정 중에서 지금 쓸 계정을 바꾼다. */
export function switchAccount(userId: string): void {
  if (state.accountIds.includes(userId) && state.activeId !== userId) save({ ...state, activeId: userId })
}

/** 한 계정에서 로그아웃. 지금 쓰던 계정이면 남은 첫 계정으로 바꾼다. */
export function signOut(userId: string): void {
  const accountIds = state.accountIds.filter((id) => id !== userId)
  save({ accountIds, activeId: state.activeId === userId ? accountIds[0] : state.activeId })
}

export function signOutAll(): void {
  save({ accountIds: [], activeId: undefined })
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useAccounts(): AccountState {
  return useSyncExternalStore(subscribe, () => state)
}
