import { useState } from 'react'
import { Link } from 'react-router'
import { analyzeJob } from '../api/jobs'
import type { Confidence, Job } from '../api/types'
import { JobFrame } from '../components/JobFrame'
import { ErrorNotice, Notice } from '../components/Notice'
import { useWorkspace } from '../hooks/useWorkspace'
import { formatDateTime, formatPercent } from '../lib/format'
import { paths } from '../lib/paths'

const CONFIDENCE_LABEL: Record<keyof Confidence, string> = {
  visual: '시각 인식',
  db_consistency: 'DB 정합성',
  vlm_reasoning: 'VLM 추론',
  overall: '종합',
}

/** 와이어프레임 5 — 해석 결과: 마킹 해석 · 용접 조건 · 신뢰도 · 판단 근거 */
export function JobResultPage() {
  return (
    <JobFrame
      section="해석 결과"
      description="인식한 마킹을 DB(문자/기호·조립 경로·용접 기준)와 대조해 판별한 용접 조건과 신뢰도, 판단 근거입니다."
    >
      {(job, reload) => <JobResult job={job} onChange={reload} />}
    </JobFrame>
  )
}

function JobResult({ job, onChange }: { job: Job; onChange: () => void }) {
  const workspace = useWorkspace()
  const { confidence } = job

  return (
    <>
      {job.status === 'draft' && <AnalyzePanel workspaceId={workspace.id} jobId={job.id} onDone={onChange} />}

      {job.needs_review.length > 0 && (
        <Notice tone="warning">
          확인이 필요한 항목이 {job.needs_review.length}개 있습니다.
          <Link className="btn btn--small" to={paths.jobReview(workspace.id, job.id)}>
            작업자 확인으로
          </Link>
        </Notice>
      )}

      <section className="section">
        <h2 className="section-title">작업 정보</h2>
        <dl className="props">
          <dt>조립 경로</dt>
          <dd className="mono">{job.assembly_path ?? '—'}</dd>
          <dt>생성일</dt>
          <dd>{formatDateTime(job.created_at)}</dd>
          <dt>관련 작업</dt>
          <dd>
            {job.related_job_ids.length === 0
              ? '—'
              : job.related_job_ids.map((id, index) => (
                  <span key={id}>
                    {index > 0 && ', '}
                    <Link to={paths.job(workspace.id, id)}>{id}</Link>
                  </span>
                ))}
          </dd>
        </dl>
      </section>

      <section className="section">
        <h2 className="section-title">표기 해석</h2>
        {job.marking ? (
          <dl className="props">
            <dt>인식 원문</dt>
            <dd className="mono">{job.marking.raw_text}</dd>
            <dt>기호</dt>
            <dd>{job.marking.symbols.join(', ') || '—'}</dd>
            <dt>해석</dt>
            <dd>{job.marking.interpretation}</dd>
          </dl>
        ) : (
          <p className="state">아직 해석 결과가 없습니다.</p>
        )}
      </section>

      <section className="section">
        <h2 className="section-title">용접 조건</h2>
        {job.welding_condition ? (
          <dl className="props">
            <dt>이음 형태</dt>
            <dd>{job.welding_condition.joint_type}</dd>
            <dt>용접 공정</dt>
            <dd>{job.welding_condition.process}</dd>
            <dt>자세</dt>
            <dd>{job.welding_condition.position}</dd>
            <dt>전류 (A)</dt>
            <dd>{job.welding_condition.current_a}</dd>
            <dt>전압 (V)</dt>
            <dd>{job.welding_condition.voltage_v}</dd>
            <dt>속도 (cm/min)</dt>
            <dd>{job.welding_condition.speed_cm_min}</dd>
          </dl>
        ) : (
          <p className="state">아직 판별한 용접 조건이 없습니다.</p>
        )}
      </section>

      <section className="section">
        <h2 className="section-title">신뢰도</h2>
        {confidence ? (
          <dl className="props">
            {(Object.keys(CONFIDENCE_LABEL) as (keyof Confidence)[]).map((key) => (
              <div key={key}>
                <dt>{CONFIDENCE_LABEL[key]}</dt>
                <dd>
                  <meter min={0} max={100} low={70} high={85} optimum={100} value={confidence[key]} />{' '}
                  {formatPercent(confidence[key])}
                </dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="state">아직 신뢰도가 없습니다.</p>
        )}
      </section>

      <section className="section">
        <h2 className="section-title">판단 근거</h2>
        {job.evidence.length > 0 ? (
          <ul className="plain-list">
            {job.evidence.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <p className="state">판단 근거가 없습니다.</p>
        )}
      </section>

      <p className="button-row section">
        <Link className="btn" to={paths.jobReview(workspace.id, job.id)}>
          작업자 확인
        </Link>
        <Link className="btn btn--primary" to={paths.jobSummary(workspace.id, job.id)}>
          승인 요약본
        </Link>
      </p>
    </>
  )
}

interface AnalyzePanelProps {
  workspaceId: string
  jobId: string
  onDone: () => void
}

/** 초안 작업: 분석 실행 (파이프라인 구현 전까지 501) */
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
      <Notice tone="info">
        아직 분석하지 않은 작업입니다.
        <button type="button" className="btn btn--small" onClick={run} disabled={running}>
          {running ? '분석 중…' : '분석 실행'}
        </button>
      </Notice>
      {error !== undefined && <ErrorNotice error={error} />}
    </>
  )
}
