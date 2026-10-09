import { isApiError } from '../api/client'

/** 501: 백엔드에서 아직 구현하지 않은 기능 */
export const NOT_IMPLEMENTED_MESSAGE = '아직 준비되지 않은 기능이에요.'

const UNREACHABLE_MESSAGE = '서버에 연결할 수 없어요. 백엔드가 켜져 있는지 확인해 주세요.'

/** 프록시·게이트웨이가 백엔드에 닿지 못했을 때의 상태 (Vite 개발 서버 프록시는 502) */
const GATEWAY_STATUSES = [502, 503, 504]

/** API 오류를 화면에 보여 줄 문장으로 바꾼다. 백엔드가 detail 문자열을 주면 그대로 쓴다. */
export function errorMessage(error: unknown): string {
  if (isApiError(error)) {
    if (error.status === 501) return NOT_IMPLEMENTED_MESSAGE
    if (typeof error.detail === 'string') return error.detail
    if (GATEWAY_STATUSES.includes(error.status)) return UNREACHABLE_MESSAGE
    if (error.status === 404) return '요청한 항목을 찾을 수 없어요.'
    if (error.status === 413) return '사진이 너무 커요. 20MB 이하로 올려 주세요.'
    if (error.status === 422) return `입력값을 확인해 주세요. ${validationMessages(error.detail)}`.trim()
    return `요청을 처리하지 못했어요 (${error.message}).`
  }
  // fetch 자체가 실패 (백엔드 꺼짐·네트워크 오류)
  if (error instanceof TypeError) return UNREACHABLE_MESSAGE
  // 화면에서 직접 만든 안내 (예: new Error('바꾼 값이 없어요.'))
  if (error instanceof Error && error.message) return error.message
  return '알 수 없는 문제가 생겼어요.'
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
