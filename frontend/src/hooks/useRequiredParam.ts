import { useParams } from 'react-router'

/** 라우트 경로 파라미터(예: ':jobId')를 문자열로 꺼낸다. 라우트 정의상 항상 있는 값에만 쓴다. */
export function useRequiredParam(name: string): string {
  const value = useParams()[name]
  if (value === undefined) throw new Error(`라우트 파라미터 '${name}' 가 없습니다.`)
  return value
}
