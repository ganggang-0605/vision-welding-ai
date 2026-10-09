/** 화면 표시용 포맷 함수 */

const dateTimeFormat = new Intl.DateTimeFormat('ko-KR', { month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit' })
const timeFormat = new Intl.DateTimeFormat('ko-KR', { hour: 'numeric', minute: '2-digit' })
const dayFormat = new Intl.DateTimeFormat('ko-KR', { month: 'long', day: 'numeric' })

/** 값이 없을 때 표시 */
export const EMPTY = '-'

/** ISO 날짜·시간 → "10월 9일 오후 12:38" (값이 없으면 '-') */
export function formatDateTime(value: string | null | undefined): string {
  const date = toDate(value)
  return date ? dateTimeFormat.format(date) : value || EMPTY
}

/**
 * 목록용 짧은 날짜: 오늘이면 "오후 2:20", 어제면 "어제", 그 외 "10월 7일".
 * 메일 앱 목록과 같은 규칙이다.
 */
export function formatShortDate(value: string | null | undefined, now = new Date()): string {
  const date = toDate(value)
  if (!date) return EMPTY
  const days = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000)
  if (days === 0) return timeFormat.format(date)
  if (days === 1) return '어제'
  return dayFormat.format(date)
}

/** 0~100 신뢰도 → "68" (단위는 화면에서 붙인다, 값이 없으면 '-') */
export function formatScore(value: number | null | undefined): string {
  return value === null || value === undefined ? EMPTY : String(Math.round(value))
}

/** 0~100 신뢰도 → "68%" (값이 없으면 '-') */
export function formatPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? EMPTY : `${Math.round(value)}%`
}

function toDate(value: string | null | undefined): Date | undefined {
  if (!value) return undefined
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? undefined : date
}

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
}
