import { Check } from '@phosphor-icons/react'
import { useState } from 'react'
import { Link } from 'react-router'
import { analyzeJob } from '../api/jobs'
import type { Confidence, Job } from '../api/types'
import { JobFrame } from '../components/JobFrame'
import { ErrorNotice, Notice } from '../components/Notice'
import { useWorkspace } from '../hooks/useWorkspace'
import { formatScore } from '../lib/format'
import { jointTypeLabel, positionLabel, withUnit } from '../lib/labels'
import { paths } from '../lib/paths'
import styles from './JobResultPage.module.css'

/** 종합 신뢰도 아래에 나눠 보여 줄 세 가지 (README '신뢰도' 표 순서) */
const CONFIDENCE_PARTS: { key: Exclude<keyof Confidence, 'overall'>; label: string }[] = [
  { key: 'visual', label: '시각 인식' },
  { key: 'db_consistency', label: 'DB 정합성' },
  { key: 'vlm_reasoning', label: 'VLM 추론' },
]

/** 와이어프레임 5 — 해석 결과: 인식한 표기, 신뢰도, 용접 조건, 판단 근거 */
export function JobResultPage() {
  return <JobFrame section="해석 결과">{(job, reload) => <JobResult job={job} onChange={reload} />}</JobFrame>
}

function JobResult({ job, onChange }: { job: Job; onChange: () => void }) {
  const workspace = useWorkspace()
  const { marking, confidence, welding_condition: condition } = job

  return (
    <>
      {job.status === 'draft' && <AnalyzePanel workspaceId={workspace.id} jobId={job.id} onDone={onChange} />}

      {job.needs_review.length > 0 && (
        <Notice
          tone="warning"
          title={`확인이 필요한 항목이 ${job.needs_review.length}개 있어요`}
          action={
            <Link className="btn" to={paths.jobReview(workspace.id, job.project_id, job.id)}>
              검토하기
            </Link>
          }
        >
          {job.needs_review[0]}
        </Notice>
      )}

      <div className={styles.hero}>
        <section aria-labelledby="marking-title">
          <h2 id="marking-title" className="section-title">
            인식한 표기
          </h2>
          {marking ? (
            <>
              <p className={styles.plate}>{marking.raw_text}</p>
              <p className={styles.interpretation}>{marking.interpretation}</p>
            </>
          ) : (
            <p className="state">아직 해석 결과가 없어요.</p>
          )}
        </section>

        <section aria-labelledby="confidence-title">
          <h2 id="confidence-title" className="section-title">
            신뢰도
          </h2>
          {confidence ? (
            <>
              <p className={styles.overall}>
                <span className={styles.overallValue}>{formatScore(confidence.overall)}</span>
                <span className="stat-unit">%</span>
                <span className={styles.overallLabel}>종합</span>
              </p>
              <dl className={styles.parts}>
                {CONFIDENCE_PARTS.map(({ key, label }) => (
                  <div key={key}>
                    <dt>{label}</dt>
                    <dd>{formatScore(confidence[key])}%</dd>
                  </div>
                ))}
              </dl>
            </>
          ) : (
            <p className="state">아직 신뢰도가 없어요.</p>
          )}
        </section>
      </div>

      <div className={styles.columns}>
        <section className="section" aria-labelledby="condition-title">
          <h2 id="condition-title" className="section-title">
            추천 용접 조건
          </h2>
          {condition ? (
            <dl className="group">
              <div className="group-row">
                <dt>이음 형태</dt>
                <dd>{jointTypeLabel(condition.joint_type)}</dd>
              </div>
              <div className="group-row">
                <dt>공법</dt>
                <dd>{condition.process}</dd>
              </div>
              <div className="group-row">
                <dt>자세</dt>
                <dd>{positionLabel(condition.position)}</dd>
              </div>
              <div className="group-row">
                <dt>전류</dt>
                <dd>{withUnit(condition.current_a, 'A')}</dd>
              </div>
              <div className="group-row">
                <dt>전압</dt>
                <dd>{withUnit(condition.voltage_v, 'V')}</dd>
              </div>
              <div className="group-row">
                <dt>속도</dt>
                <dd>{withUnit(condition.speed_cm_min, 'cm/min')}</dd>
              </div>
            </dl>
          ) : (
            <p className="state">아직 고른 용접 조건이 없어요.</p>
          )}
        </section>

        <section className="section" aria-labelledby="evidence-title">
          <h2 id="evidence-title" className="section-title">
            판단 근거
          </h2>
          {job.evidence.length > 0 ? (
            <ul className="check-list">
              {job.evidence.map((item) => (
                <li key={item}>
                  <Check size={16} weight="bold" aria-hidden="true" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="state">판단 근거가 없어요.</p>
          )}
        </section>
      </div>

      {job.related_job_ids.length > 0 && (
        <section className="section" aria-labelledby="related-title">
          <h2 id="related-title" className="section-title">
            연결된 작업
          </h2>
          <ul className="group">
            {job.related_job_ids.map((id) => (
              <li key={id} className="group-row">
                {/* 다른 프로젝트의 작업일 수도 있다. 주소가 다르면 JobFrame 이 맞는 프로젝트로 옮긴다. */}
                <Link to={paths.job(workspace.id, job.project_id, id)}>{id}</Link>
                <span />
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  )
}

interface AnalyzePanelProps {
  workspaceId: string
  jobId: string
  onDone: () => void
}

/** 해석 전 작업: 해석 시작 (파이프라인 구현 전까지 501) */
function AnalyzePanel({ workspaceId, jobId, onDone }: AnalyzePanelProps) {
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<unknown>()

  const run = async () => {
    setRunning(true)
    setError(undefined)
    try {
      await analyzeJob(workspaceId, jobId)
      onDone()
    } catch (err) {
      setError(err)
    } finally {
      setRunning(false)
    }
  }

  return (
    <>
      <Notice
        title="아직 해석하지 않은 작업이에요"
        action={
          <button type="button" className="btn btn--primary" onClick={run} disabled={running}>
            {running ? '해석 중' : '해석 시작'}
          </button>
        }
      >
        사진을 올렸다면 지금 해석할 수 있어요.
      </Notice>
      {error !== undefined && <ErrorNotice error={error} />}
    </>
  )
}
