import { isRouteErrorResponse, Link, useRouteError } from 'react-router'
import { PageHeader } from '../components/PageHeader'

/** 라우트 렌더링 중 예기치 못한 오류가 났을 때 (최상위 ErrorBoundary) */
export function RouteErrorPage() {
  const error = useRouteError()
  const detail = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : String(error)

  return (
    <div className="page page--narrow">
      <PageHeader title="문제가 발생했습니다" description="화면을 그리는 중 오류가 났습니다. 새로고침하거나 홈으로 이동해 주세요." />
      <pre className="code-block">{detail}</pre>
      <p className="button-row">
        <Link className="btn btn--primary" to="/">
          홈으로
        </Link>
      </p>
    </div>
  )
}
