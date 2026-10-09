import type { ReactNode } from 'react'
import { isApiError } from '../api/client'
import { errorMessage } from '../lib/errors'

interface NoticeProps {
  tone?: 'info' | 'warning' | 'error'
  children: ReactNode
}

/** 안내·경고·오류 박스 (Notion 콜아웃 형태) */
export function Notice({ tone = 'info', children }: NoticeProps) {
  return (
    <div className={`notice notice--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      {children}
    </div>
  )
}

interface ErrorNoticeProps {
  error: unknown
  /** 있으면 '다시 시도' 버튼을 보여준다. */
  onRetry?: () => void
}

/** API 오류 표시. 501(미구현)은 오류가 아닌 경고 톤으로 보여준다. */
export function ErrorNotice({ error, onRetry }: ErrorNoticeProps) {
  const notImplemented = isApiError(error, 501)
  return (
    <Notice tone={notImplemented ? 'warning' : 'error'}>
      <span>{errorMessage(error)}</span>
      {onRetry && !notImplemented && (
        <button type="button" className="btn btn--small" onClick={onRetry}>
          다시 시도
        </button>
      )}
    </Notice>
  )
}
