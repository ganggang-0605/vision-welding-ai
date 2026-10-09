import { Link } from 'react-router'
import { PageHeader } from '../components/PageHeader'

/** 없는 주소 (워크스페이스 안이면 사이드바와 함께, 밖이면 단독으로 보인다) */
export function NotFoundPage() {
  return (
    <div className="page page--narrow">
      <PageHeader title="페이지를 찾을 수 없어요" description="주소가 잘못됐거나 옮겨진 페이지예요." />
      <Link className="btn btn--primary" to="/">
        처음으로
      </Link>
    </div>
  )
}
