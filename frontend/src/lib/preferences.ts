/**
 * 내 환경설정 (모든 워크스페이스에 공통, 이 브라우저에만 기억): 화면 모드, 글씨 크기.
 * <html data-theme / data-text-size> 를 바꾸면 index.css 가 따라 바뀐다. 기본값이면 속성을 지운다.
 * 첫 화면이 깜빡이지 않도록 index.html 의 인라인 스크립트가 같은 키로 먼저 적용한다 (키·값을 바꾸면 둘 다 고친다).
 */
import { useSyncExternalStore } from 'react'

export type ThemePreference = 'system' | 'light' | 'dark'
export type TextSize = 'small' | 'default' | 'large'

export const THEME_OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: 'system', label: '시스템' },
  { value: 'light', label: '라이트' },
  { value: 'dark', label: '다크' },
]

export const TEXT_SIZE_OPTIONS: { value: TextSize; label: string }[] = [
  { value: 'small', label: '작게' },
  { value: 'default', label: '기본' },
  { value: 'large', label: '크게' },
]

interface Preference<T extends string> {
  storageKey: string
  attribute: 'theme' | 'textSize'
  fallback: T
  values: readonly T[]
}

const THEME: Preference<ThemePreference> = {
  storageKey: 'vwa:theme',
  attribute: 'theme',
  fallback: 'system',
  values: ['system', 'light', 'dark'],
}

const TEXT_SIZE: Preference<TextSize> = {
  storageKey: 'vwa:text-size',
  attribute: 'textSize',
  fallback: 'default',
  values: ['small', 'default', 'large'],
}

const listeners = new Set<() => void>()
const current = new Map<string, string>()

function read<T extends string>(preference: Preference<T>): T {
  if (!current.has(preference.storageKey)) {
    let value: string | null = null
    try {
      value = localStorage.getItem(preference.storageKey)
    } catch {
      // 저장소를 못 쓰면 기본값
    }
    current.set(preference.storageKey, preference.values.includes(value as T) ? (value as T) : preference.fallback)
  }
  return current.get(preference.storageKey) as T
}

function write<T extends string>(preference: Preference<T>, value: T): void {
  try {
    if (value === preference.fallback) localStorage.removeItem(preference.storageKey)
    else localStorage.setItem(preference.storageKey, value)
  } catch {
    // 이번 방문 동안만 적용된다.
  }
  if (value === preference.fallback) delete document.documentElement.dataset[preference.attribute]
  else document.documentElement.dataset[preference.attribute] = value
  current.set(preference.storageKey, value)
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function usePreference<T extends string>(preference: Preference<T>): [T, (value: T) => void] {
  const value = useSyncExternalStore(subscribe, () => read(preference))
  return [value, (next: T) => write(preference, next)]
}

/** 화면 모드 (시스템 / 라이트 / 다크) */
export function useThemePreference(): [ThemePreference, (value: ThemePreference) => void] {
  return usePreference(THEME)
}

/** 글씨 크기 (작게 / 기본 / 크게). 화면 전체의 rem 기준 크기를 바꾼다. */
export function useTextSize(): [TextSize, (value: TextSize) => void] {
  return usePreference(TEXT_SIZE)
}
