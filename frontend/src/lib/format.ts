/** 화면 표시용 포맷 함수 */

const dateTimeFormat = new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' })

/** ISO 날짜·시간 → "2026. 10. 9. 오후 12:38" (값이 없거나 잘못되면 '—') */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : dateTimeFormat.format(date)
}

/** 0~100 신뢰도 → "68%" (값이 없으면 '—') */
export function formatPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${Math.round(value)}%`
}
