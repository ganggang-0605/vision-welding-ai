import { useEffect, useState } from 'react'
import { getHealth } from '../api/client'

type Status = 'checking' | 'connected' | 'disconnected'

const LABEL: Record<Status, string> = {
  checking: '확인 중…',
  connected: '연결됨',
  disconnected: '연결 안 됨',
}

/** 백엔드가 연결만 받고 응답하지 않을 때 '연결 안 됨'으로 바꾸기까지 기다리는 시간 */
const HEALTH_TIMEOUT_MS = 5000

/** /api/health 를 호출해 백엔드 연결 상태를 보여준다. */
export function BackendStatus() {
  const [status, setStatus] = useState<Status>('checking')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let timedOut = false
    const timer = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, HEALTH_TIMEOUT_MS)

    getHealth(controller.signal)
      .then((res) => {
        if (!controller.signal.aborted) {
          setStatus(res.status === 'ok' ? 'connected' : 'disconnected')
        }
      })
      .catch(() => {
        // 언마운트·재시도로 중단된 경우는 무시하고, 타임아웃은 '연결 안 됨'으로 표시
        if (!controller.signal.aborted || timedOut) setStatus('disconnected')
      })
      .finally(() => clearTimeout(timer))

    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [attempt])

  const recheck = () => {
    setStatus('checking')
    setAttempt((n) => n + 1)
  }

  return (
    <div className="backend-status">
      <span className={`status-dot status-dot--${status}`} aria-hidden="true" />
      <span role="status" aria-live="polite">
        백엔드 서버: <strong>{LABEL[status]}</strong>
      </span>
      <button type="button" onClick={recheck} disabled={status === 'checking'}>
        다시 확인
      </button>
    </div>
  )
}
