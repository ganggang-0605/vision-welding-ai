import type { ReactNode } from 'react'
import type { AsyncState } from '../hooks/useAsync'
import { ErrorNotice } from './Notice'

interface AsyncViewProps<T> {
  state: AsyncState<T>
  /** 불러오기에 성공했을 때 그릴 내용 */
  children: (data: T) => ReactNode
  /** true 를 돌려주면 children 대신 empty 를 보여준다. */
  isEmpty?: (data: T) => boolean
  empty?: ReactNode
  /** true 면 다시 불러오는(reload) 동안 직전 데이터를 그대로 보여 준다 (화면 깜빡임·입력 상태 유지). */
  keepPreviousData?: boolean
}

/** useAsync 결과의 로딩·오류·빈 상태를 공통 모양으로 그린다. */
export function AsyncView<T>({
  state,
  children,
  isEmpty,
  empty = '항목이 없습니다.',
  keepPreviousData = false,
}: AsyncViewProps<T>) {
  if (state.loading && !(keepPreviousData && state.data !== undefined)) {
    return (
      <p className="state" role="status">
        불러오는 중…
      </p>
    )
  }
  if (state.error !== undefined) return <ErrorNotice error={state.error} onRetry={state.reload} />
  if (state.data === undefined) return null
  if (isEmpty?.(state.data)) return <p className="state">{empty}</p>
  return children(state.data)
}
