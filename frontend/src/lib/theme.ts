/**
 * 화면 모드 (시스템 / 라이트 / 다크). 고른 값은 이 브라우저에만 기억한다.
 * <html data-theme> 를 바꾸면 index.css 의 토큰이 따라 바뀐다. 'system' 이면 속성을 지워 OS 설정을 따른다.
 * 첫 화면이 깜빡이지 않도록 index.html 의 인라인 스크립트가 같은 키로 먼저 적용한다 (키를 바꾸면 둘 다 고친다).
 */
import { useSyncExternalStore } from 'react'

export type ThemePreference = 'system' | 'light' | 'dark'

export const THEME_OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: 'system', label: '시스템' },
  { value: 'light', label: '라이트' },
  { value: 'dark', label: '다크' },
]

const STORAGE_KEY = 'vwa:theme'
const listeners = new Set<() => void>()

function read(): ThemePreference {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch {
    return 'system'
  }
}

function apply(preference: ThemePreference): void {
  if (preference === 'system') delete document.documentElement.dataset.theme
  else document.documentElement.dataset.theme = preference
}

export function setThemePreference(preference: ThemePreference): void {
  try {
    if (preference === 'system') localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, preference)
  } catch {
    // 저장소를 못 쓰는 환경: 이번 방문 동안만 적용된다.
  }
  apply(preference)
  current = preference
  listeners.forEach((listener) => listener())
}

let current = read()

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** 지금 고른 화면 모드와 바꾸는 함수 */
export function useThemePreference(): [ThemePreference, (preference: ThemePreference) => void] {
  const preference = useSyncExternalStore(subscribe, () => current)
  return [preference, setThemePreference]
}
