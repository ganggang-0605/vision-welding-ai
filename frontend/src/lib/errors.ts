import { isApiError } from '../api/client'

/** 501: 백엔드 파이프라인(업로드·분석·재해석)이 아직 구현되지 않았을 때 */
export const NOT_IMPLEMENTED_MESSAGE = '아직 구현되지 않음(501) — 백엔드 파이프라인이 준비되면 동작합니다.'

const UNREACHABLE_MESSAGE = '서버에 연결할 수 없습니다. 백엔드가 실행 중인지 확인해 주세요.'

/** 프록시·게이트웨이가 백엔드에 닿지 못했을 때의 상태 (Vite 개발 서버 프록시는 502) */
const GATEWAY_STATUSES = [502, 503, 504]

/** API 오류를 화면에 보여 줄 문장으로 바꾼다. 백엔드가 detail 문자열을 주면 그대로 쓴다. */
export function errorMessage(error: unknown): string {
  if (isApiError(error)) {
    if (error.status === 501) return NOT_IMPLEMENTED_MESSAGE
    if (typeof error.detail === 'string') return error.detail
    if (GATEWAY_STATUSES.includes(error.status)) return UNREACHABLE_MESSAGE
    if (error.status === 404) return '요청한 항목을 찾을 수 없습니다.'
    if (error.status === 422) return `입력값을 확인해 주세요. ${validationMessages(error.detail)}`.trim()
    return `요청에 실패했습니다 (${error.message}).`
  }
  // fetch 자체가 실패 (백엔드 꺼짐·네트워크 오류)
  if (error instanceof TypeError) return UNREACHABLE_MESSAGE
  return '알 수 없는 오류가 발생했습니다.'
}

/** FastAPI 422 detail 배열 `[{loc, msg}]` → "name: ... / description: ..." */
function validationMessages(detail: unknown): string {
  if (!Array.isArray(detail)) return ''
  return detail
    .map((item: { loc?: unknown[]; msg?: string }) => {
      const field = item.loc?.filter((part) => part !== 'body').join('.')
      return field ? `${field}: ${item.msg ?? ''}` : (item.msg ?? '')
    })
    .join(' / ')
}
