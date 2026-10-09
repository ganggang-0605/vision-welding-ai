import { Info, WarningCircle } from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { isApiError } from '../api/client'
import { errorMessage } from '../lib/errors'

interface NoticeProps {
  tone?: 'info' | 'warning' | 'error'
  /** 굵은 첫 줄. 없으면 children 만 한 줄로 보여 준다. */
  title?: ReactNode
  /** 오른쪽 끝 버튼 */
  action?: ReactNode
  children?: ReactNode
}

/** 안내·경고·오류. 색 상자 대신 회색 면 하나에 아이콘 색으로만 구분한다. */
export function Notice({ tone = 'info', title, action, children }: NoticeProps) {
  const Icon = tone === 'info' ? Info : WarningCircle
  return (
    <div className={`notice notice--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon size={20} weight={tone === 'info' ? 'regular' : 'fill'} aria-hidden="true" />
      <div className="notice-body">
        {title ? (
          <>
            <p className="notice-title">{title}</p>
            {children && <p className="notice-text">{children}</p>}
          </>
        ) : (
          children
        )}
      </div>
      {action}
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
    <Notice
      tone={notImplemented ? 'warning' : 'error'}
      action={
        onRetry &&
        !notImplemented && (
          <button type="button" className="btn btn--small" onClick={onRetry}>
            다시 시도
          </button>
        )
      }
    >
      {errorMessage(error)}
    </Notice>
  )
}
