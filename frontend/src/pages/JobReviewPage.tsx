import { useId, useState, type FormEvent } from 'react'
import { reviewJob } from '../api/jobs'
import type { Job, ReviewAction, ReviewRequest, WeldingCondition } from '../api/types'
import { JobFrame } from '../components/JobFrame'
import { ErrorNotice, Notice } from '../components/Notice'
import { useWorkspace } from '../hooks/useWorkspace'

const CONDITION_FIELDS: { key: keyof WeldingCondition; label: string }[] = [
  { key: 'joint_type', label: '이음 형태' },
  { key: 'process', label: '용접 공정' },
  { key: 'position', label: '자세' },
  { key: 'current_a', label: '전류 (A)' },
  { key: 'voltage_v', label: '전압 (V)' },
  { key: 'speed_cm_min', label: '속도 (cm/min)' },
]

const EMPTY_CONDITION: WeldingCondition = {
  joint_type: '',
  process: '',
  position: '',
  current_a: '',
  voltage_v: '',
  speed_cm_min: '',
}

/** 와이어프레임 6 — 작업자 확인: 신뢰도 미달 항목을 보고 재해석하거나 직접 해석한다. */
export function JobReviewPage() {
  return (
    <JobFrame
      section="작업자 확인"
      description="신뢰도가 기준치에 못 미친 항목입니다. 맥락을 덧붙여 다시 해석하거나, 해석 결과를 직접 입력합니다."
    >
      {(job, reload) => <ReviewForm job={job} onReviewed={reload} />}
    </JobFrame>
  )
}

function ReviewForm({ job, onReviewed }: { job: Job; onReviewed: () => void }) {
  const workspace = useWorkspace()
  const contextId = useId()
  const interpretationId = useId()
  const [action, setAction] = useState<ReviewAction>('reinterpret')
  const [context, setContext] = useState('')
  const [interpretation, setInterpretation] = useState(job.marking?.interpretation ?? '')
  const [condition, setCondition] = useState<WeldingCondition>(job.welding_condition ?? EMPTY_CONDITION)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<unknown>()
  const [done, setDone] = useState(false)

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    // TODO: manual 의 values 형식은 백엔드 재해석 구현 때 확정한다.
    const body: ReviewRequest =
      action === 'reinterpret'
        ? { action, context: context.trim() || null }
        : { action, values: { interpretation, welding_condition: condition } }
    setSubmitting(true)
    setError(undefined)
    setDone(false)
    try {
      await reviewJob(workspace.id, job.id, body)
      setDone(true)
      onReviewed()
    } catch (err) {
      setError(err)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <section className="section">
        <h2 className="section-title">확인이 필요한 항목</h2>
        {job.needs_review.length > 0 ? (
          <ul className="plain-list">
            {job.needs_review.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <p className="state">확인이 필요한 항목이 없습니다.</p>
        )}
        {job.marking && (
          <p className="field-hint">
            인식 원문: <span className="mono">{job.marking.raw_text}</span>
          </p>
        )}
      </section>

      <section className="section">
        <h2 className="section-title">확인 방법</h2>
        <form className="form" onSubmit={onSubmit}>
          <fieldset className="field">
            <legend className="field-label">처리 방식</legend>
            <label className="choice">
              <input
                type="radio"
                name="action"
                value="reinterpret"
                checked={action === 'reinterpret'}
                onChange={() => setAction('reinterpret')}
              />
              맥락을 추가해 다시 해석
            </label>
            <label className="choice">
              <input
                type="radio"
                name="action"
                value="manual"
                checked={action === 'manual'}
                onChange={() => setAction('manual')}
              />
              직접 해석 입력
            </label>
          </fieldset>

          {action === 'reinterpret' ? (
            <div className="field">
              <label htmlFor={contextId} className="field-label">
                추가 맥락
              </label>
              <textarea
                id={contextId}
                className="input"
                placeholder="예: 이 부재는 S1 소조립의 필렛 용접부입니다. 두 번째 글자는 B가 아니라 8입니다."
                value={context}
                onChange={(event) => setContext(event.target.value)}
              />
            </div>
          ) : (
            <>
              <div className="field">
                <label htmlFor={interpretationId} className="field-label">
                  해석
                </label>
                <textarea
                  id={interpretationId}
                  className="input"
                  value={interpretation}
                  onChange={(event) => setInterpretation(event.target.value)}
                />
              </div>
              <fieldset className="field">
                <legend className="field-label">용접 조건</legend>
                <div className="grid-2">
                  {CONDITION_FIELDS.map(({ key, label }) => (
                    <label key={key} className="field">
                      <span className="field-hint">{label}</span>
                      <input
                        className="input"
                        value={condition[key]}
                        onChange={(event) => setCondition({ ...condition, [key]: event.target.value })}
                      />
                    </label>
                  ))}
                </div>
              </fieldset>
            </>
          )}

          {error !== undefined && <ErrorNotice error={error} />}
          {done && <Notice tone="info">확인 내용을 반영했습니다.</Notice>}

          <p className="button-row">
            <button type="submit" className="btn btn--primary" disabled={submitting}>
              {submitting ? '처리 중…' : action === 'reinterpret' ? '다시 해석' : '해석 저장'}
            </button>
          </p>
        </form>
      </section>
    </>
  )
}
