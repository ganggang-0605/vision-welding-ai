import { WarningCircle } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { getHealth } from '../api/client'

type Status = 'checking' | 'connected' | 'disconnected'

/** 백엔드가 연결만 받고 응답하지 않을 때 '연결 안 됨'으로 바꾸기까지 기다리는 시간 */
const HEALTH_TIMEOUT_MS = 5000

/**
 * /api/health 로 백엔드 연결을 확인한다.
 * 정상일 때는 아무것도 그리지 않고, 연결이 끊겼을 때만 사이드바 아래에 알린다.
 */
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
    <div role="status" aria-live="polite">
      {status === 'disconnected' && (
        <div className="backend-status">
          <WarningCircle size={16} weight="fill" aria-hidden="true" />
          <span>서버에 연결할 수 없어요</span>
          <button type="button" className="btn btn--plain btn--small" onClick={recheck}>
            다시 확인
          </button>
        </div>
      )}
    </div>
  )
}
