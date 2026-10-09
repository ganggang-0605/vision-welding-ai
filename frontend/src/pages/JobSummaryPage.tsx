import { Check, Copy, DownloadSimple, WarningCircle } from '@phosphor-icons/react'
import { useEffect, useId, useState, type FormEvent, type ReactNode } from 'react'
import { isApiError } from '../api/client'
import { approveJob, exportJob } from '../api/jobs'
import type { Confidence, Job } from '../api/types'
import { AsyncView } from '../components/AsyncView'
import { JobFrame } from '../components/JobFrame'
import { ErrorNotice } from '../components/Notice'
import { useAsync } from '../hooks/useAsync'
import { useWorkspace } from '../hooks/useWorkspace'
import { downloadJson } from '../lib/download'
import { formatDateTime, formatScore } from '../lib/format'
import { APPROVABLE_STATUSES, cellSideLabel, jointTypeLabel, positionLabel, withUnit } from '../lib/labels'
import styles from './JobSummaryPage.module.css'

const STATS: { key: keyof Confidence; label: string }[] = [
  { key: 'visual', label: '시각 인식' },
  { key: 'db_consistency', label: 'DB 정합성' },
  { key: 'vlm_reasoning', label: 'VLM 추론' },
  { key: 'overall', label: '종합' },
]

/** '복사됨' 표시를 유지하는 시간 */
const COPIED_MS = 1600

/** 와이어프레임 7 — 승인 요약본 · 로봇 연계 JSON 내보내기. 문서처럼 위에서 아래로 읽힌다. */
export function JobSummaryPage() {
  return (
    <JobFrame section="요약본">
      {(job, reload) => (
        <div className={styles.document}>
          <Summary job={job} />
          {APPROVABLE_STATUSES.includes(job.status) && <ApproveForm job={job} onApproved={reload} />}
          <ExportSection job={job} />
        </div>
      )}
    </JobFrame>
  )
}

function Summary({ job }: { job: Job }) {
  const { welding_condition: condition, confidence } = job
  return (
    <>
      <section className="section" aria-labelledby="result-title">
        <h2 id="result-title" className={styles.result}>
          {condition ? `${jointTypeLabel(condition.joint_type)} 용접` : '용접 조건 없음'}
        </h2>
        {job.marking && <p className={styles.resultDesc}>{job.marking.interpretation}</p>}
        {job.approved_by && (
          <p className={styles.approved}>
            {job.approved_by}님이 {formatDateTime(job.approved_at)}에 승인했어요.
          </p>
        )}

        {confidence && (
          <dl className={styles.stats}>
            {STATS.map(({ key, label }) => (
              <div key={key}>
                <dt className="stat-label">{label}</dt>
                <dd className="stat-value">
                  {formatScore(confidence[key])}
                  <span className="stat-unit">%</span>
                </dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      {(job.cell || job.leg_lengths.length > 0) && (
        <section className="section" aria-labelledby="cell-title">
          <h2 id="cell-title" className="section-title">
            셀 형태와 각장
          </h2>
          <dl className="group">
            {job.cell && (
              <>
                <Row label="좌">{cellSideLabel(job.cell.left)}</Row>
                <Row label="우">{cellSideLabel(job.cell.right)}</Row>
              </>
            )}
            {job.leg_lengths.map((leg, index) => (
              <Row key={`${leg.raw_text}-${index}`} label={leg.meaning ? `${leg.code} (${leg.meaning})` : leg.code}>
                {leg.size_mm}mm
              </Row>
            ))}
          </dl>
        </section>
      )}

      {condition && (
        <section className="section" aria-labelledby="condition-title">
          <h2 id="condition-title" className="section-title">
            용접 조건
          </h2>
          <dl className="group">
            <Row label="이음 형태">{jointTypeLabel(condition.joint_type)}</Row>
            <Row label="공법, 자세">
              {condition.process}, {positionLabel(condition.position)}
            </Row>
            <Row label="전류">{withUnit(condition.current_a, 'A')}</Row>
            <Row label="전압">{withUnit(condition.voltage_v, 'V')}</Row>
            <Row label="속도">{withUnit(condition.speed_cm_min, 'cm/min')}</Row>
          </dl>
        </section>
      )}

      <section className="section" aria-labelledby="review-title">
        <h2 id="review-title" className="section-title">
          확인 필요 항목
        </h2>
        {job.needs_review.length > 0 ? (
          <ul className="check-list check-list--attention">
            {job.needs_review.map((item) => (
              <li key={item}>
                <WarningCircle size={18} weight="fill" aria-hidden="true" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        ) : (
          <ul className="check-list">
            <li>
              <Check size={16} weight="bold" aria-hidden="true" />
              <span>없어요.</span>
            </li>
          </ul>
        )}
      </section>
    </>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="group-row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

function ApproveForm({ job, onApproved }: { job: Job; onApproved: () => void }) {
  const workspace = useWorkspace()
  const inputId = useId()
  // TODO(인증): 로그인 기능이 생기면 현재 사용자로 채운다.
  const [approvedBy, setApprovedBy] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<unknown>()

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError(undefined)
    try {
      await approveJob(workspace.id, job.id, { approved_by: approvedBy.trim() })
      onApproved()
    } catch (err) {
      setError(err)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="section" aria-labelledby="approve-title">
      <h2 id="approve-title" className="section-title">
        승인
      </h2>
      <p className="section-desc">승인하면 이 해석이 로봇 연계 데이터로 나가요.</p>
      <form className={styles.approve} onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor={inputId} className="field-label">
            승인하는 사람
          </label>
          <input
            id={inputId}
            className="input"
            required
            autoComplete="name"
            value={approvedBy}
            onChange={(event) => setApprovedBy(event.target.value)}
          />
        </div>
        <button type="submit" className="btn btn--primary" disabled={submitting || !approvedBy.trim()}>
          {submitting ? '승인하는 중' : '승인'}
        </button>
      </form>
      {error !== undefined && <ErrorNotice error={error} />}
    </section>
  )
}

function ExportSection({ job }: { job: Job }) {
  const workspace = useWorkspace()
  // 승인되면(status 변경) 다시 불러온다.
  const exported = useAsync((signal) => exportJob(workspace.id, job.id, signal), [workspace.id, job.id, job.status])
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), COPIED_MS)
    return () => clearTimeout(timer)
  }, [copied])

  return (
    <section className="section" aria-labelledby="export-title">
      <h2 id="export-title" className="section-title">
        로봇 연계 데이터
      </h2>
      {isApiError(exported.error, 409) ? (
        <p className="section-desc">승인한 뒤에 JSON으로 내보낼 수 있어요.</p>
      ) : (
        <AsyncView state={exported}>
          {(data) => {
            const json = JSON.stringify(data, null, 2)
            const copy = async () => {
              try {
                await navigator.clipboard.writeText(json)
                setCopied(true)
              } catch {
                // http 로 접속한 휴대폰 등 클립보드를 쓸 수 없는 환경: 내보내기 버튼으로 받으면 된다.
              }
            }
            return (
              <div className={styles.code}>
                <div className={styles.codeHeader}>
                  <span className="mono">{data.job_id}.json</span>
                  <span className="button-row">
                    <button type="button" className="btn btn--small" onClick={copy}>
                      {copied ? <Check size={14} weight="bold" aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
                      {copied ? '복사됨' : '복사'}
                    </button>
                    <button
                      type="button"
                      className="btn btn--small btn--primary"
                      onClick={() => downloadJson(`${data.job_id}.json`, data)}
                    >
                      <DownloadSimple size={14} aria-hidden="true" />
                      내보내기
                    </button>
                  </span>
                </div>
                <pre className="code-block">
                  <JsonHighlight json={json} />
                </pre>
              </div>
            )
          }}
        </AsyncView>
      )}
    </section>
  )
}

/** JSON 문자열에 키·문자열·숫자 색을 입힌다 (Xcode 라이트 테마 색). */
function JsonHighlight({ json }: { json: string }) {
  const parts: ReactNode[] = []
  const token = /("(?:\\.|[^"\\])*")(\s*:)?|\b(-?\d+(?:\.\d+)?|true|false|null)\b/g
  let last = 0
  for (const match of json.matchAll(token)) {
    const index = match.index ?? 0
    if (index > last) parts.push(json.slice(last, index))
    const [whole, str, colon, literal] = match
    if (str) {
      parts.push(
        <span key={index} className={colon ? 'code-key' : 'code-string'}>
          {str}
        </span>,
      )
      if (colon) parts.push(colon)
    } else if (literal) {
      parts.push(
        <span key={index} className="code-number">
          {literal}
        </span>,
      )
    }
    last = index + whole.length
  }
  parts.push(json.slice(last))
  return <>{parts}</>
}
