import { useEffect, type ReactNode } from 'react'

const APP_NAME = 'Vision Welding AI'

interface PageHeaderProps {
  /** 페이지 제목 (브라우저 탭 제목에도 쓰인다) */
  title: string
  /** 제목 아래 설명 */
  description?: ReactNode
  /** 제목 오른쪽의 버튼·링크 */
  actions?: ReactNode
  /** 제목 위 작은 줄 (상위 페이지 링크 등) */
  eyebrow?: ReactNode
  /** 브라우저 탭 제목. 기본값은 title */
  documentTitle?: string
}

/** 페이지 제목 영역. 브라우저 탭 제목도 함께 바꾼다. */
export function PageHeader({ title, description, actions, eyebrow, documentTitle = title }: PageHeaderProps) {
  useEffect(() => {
    document.title = `${documentTitle} · ${APP_NAME}`
  }, [documentTitle])

  return (
    <header className="page-header">
      {eyebrow && <div className="page-eyebrow">{eyebrow}</div>}
      <div className="page-title-row">
        <h1 className="page-title">{title}</h1>
        {actions && <div className="page-actions">{actions}</div>}
      </div>
      {description && <p className="page-desc">{description}</p>}
    </header>
  )
}
