/* oxlint-disable react-hooks/exhaustive-deps -- deps 를 호출한 쪽에서 받아 그대로 넘기는 범용 훅이라 정적 검사 대상이 아니다. */
import { useCallback, useEffect, useState, type DependencyList } from 'react'

export interface AsyncState<T> {
  /** 마지막으로 성공한 결과. 다시 불러오는 동안(loading)에도 직전 값을 유지한다. */
  data: T | undefined
  /** 마지막 요청이 실패했으면 그 오류, 아니면 undefined */
  error: unknown
  loading: boolean
  /** 같은 deps 로 다시 불러온다. */
  reload: () => void
}

interface Result<T> {
  /** 이 결과를 만든 요청의 deps (+ reload 횟수) */
  key: DependencyList
  data?: T
  error?: unknown
}

/**
 * 비동기 함수(주로 API 호출)의 로딩·오류 상태를 관리하는 작은 훅.
 * deps 가 바뀌거나 언마운트되면 이전 요청을 AbortSignal 로 취소한다.
 * loading 은 '현재 deps 에 대한 결과가 아직 없음'으로 렌더 중에 계산한다.
 *
 * @example
 * const jobs = useAsync((signal) => listJobs(workspaceId, {}, signal), [workspaceId])
 */
export function useAsync<T>(fn: (signal: AbortSignal) => Promise<T>, deps: DependencyList): AsyncState<T> {
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<Result<T>>()
  const key = [...deps, attempt]

  useEffect(() => {
    const controller = new AbortController()
    fn(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setResult({ key, data })
      },
      (error: unknown) => {
        if (!controller.signal.aborted) setResult({ key, error })
      },
    )
    return () => controller.abort()
    // fn 은 매 렌더마다 새로 만들어지므로 deps 로 대신 추적한다.
  }, key)

  const reload = useCallback(() => setAttempt((n) => n + 1), [])
  return {
    data: result?.data,
    error: result?.error,
    loading: result === undefined || !sameKey(result.key, key),
    reload,
  }
}

function sameKey(a: DependencyList, b: DependencyList): boolean {
  return a.length === b.length && a.every((value, i) => Object.is(value, b[i]))
}
