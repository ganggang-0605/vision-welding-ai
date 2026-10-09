import { CaretRight } from '@phosphor-icons/react'
import { useEffect, type ReactNode } from 'react'
import { Link } from 'react-router'

const APP_NAME = 'Vision Welding AI'

export interface Crumb {
  label: string
  /** 없으면 현재 페이지 */
  to?: string
}

interface PageHeaderProps {
  /** 페이지 제목 (브라우저 탭 제목에도 쓰인다) */
  title: string
  /** 제목 아래 한 줄 */
  description?: ReactNode
  /** 제목 오른쪽의 버튼·링크 */
  actions?: ReactNode
  /** 맨 위 경로 표시 (예: 작업 › A1-P1 부재 표기) */
  breadcrumb?: Crumb[]
  /** 브라우저 탭 제목. 기본값은 title */
  documentTitle?: string
}

/** 페이지 제목 영역. 브라우저 탭 제목도 함께 바꾼다. */
export function PageHeader({ title, description, actions, breadcrumb, documentTitle = title }: PageHeaderProps) {
  useEffect(() => {
    document.title = `${documentTitle} - ${APP_NAME}`
  }, [documentTitle])

  return (
    <header className="page-header">
      {breadcrumb && <Breadcrumb items={breadcrumb} />}
      <div className="page-title-row">
        <h1 className="page-title">{title}</h1>
        {actions && <div className="page-actions">{actions}</div>}
      </div>
      {description && <div className="page-desc">{description}</div>}
    </header>
  )
}

function Breadcrumb({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="현재 위치">
      <ol className="breadcrumb">
        {items.map((item, index) => (
          <li key={`${item.label}-${index}`} aria-current={item.to ? undefined : 'page'}>
            {index > 0 && <CaretRight size={12} weight="bold" aria-hidden="true" />}
            {item.to ? <Link to={item.to}>{item.label}</Link> : item.label}
          </li>
        ))}
      </ol>
    </nav>
  )
}
