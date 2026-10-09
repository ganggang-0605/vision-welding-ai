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
      <PageHeader title="화면을 그리지 못했어요" description="새로고침하거나 처음 화면으로 돌아가 주세요." />
      <pre className="code-block secondary">{detail}</pre>
      <p className="button-row">
        <Link className="btn btn--primary" to="/">
          처음으로
        </Link>
      </p>
    </div>
  )
}
