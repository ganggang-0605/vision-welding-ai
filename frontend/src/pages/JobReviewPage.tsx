import { WarningCircle } from '@phosphor-icons/react'
import { useId, useState, type FormEvent } from 'react'
import { reviewJob } from '../api/jobs'
import type { Job, ReviewAction, ReviewRequest, WeldingCondition } from '../api/types'
import { JobFrame } from '../components/JobFrame'
import { ErrorNotice, Notice } from '../components/Notice'
import { useWorkspace } from '../hooks/useWorkspace'
import styles from './JobReviewPage.module.css'

const CONDITION_FIELDS: { key: keyof WeldingCondition; label: string }[] = [
  { key: 'joint_type', label: '이음 형태' },
  { key: 'process', label: '공법' },
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

/** 와이어프레임 6 — 작업자 확인: 기준에 못 미친 항목을 보고, 맥락을 덧붙여 다시 해석하거나 직접 입력한다. */
export function JobReviewPage() {
  return <JobFrame section="작업자 확인">{(job, reload) => <ReviewForm job={job} onReviewed={reload} />}</JobFrame>
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
      <section className="section" aria-labelledby="review-items-title">
        <h2 id="review-items-title" className="section-title">
          {job.needs_review.length > 0 ? '이 부분을 확인해 주세요' : '확인할 항목이 없어요'}
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
          <p className="section-desc">모든 항목이 해석 기준을 넘었어요. 그래도 고칠 내용이 있으면 아래에서 바꿀 수 있어요.</p>
        )}
        {job.marking && (
          <p className={styles.raw}>
            <span className="secondary">인식한 표기</span>
            <span className="mono">{job.marking.raw_text}</span>
          </p>
        )}
      </section>

      <section className="section" aria-labelledby="review-action-title">
        <h2 id="review-action-title" className="section-title">
          어떻게 할까요?
        </h2>
        <form className="form" onSubmit={onSubmit}>
          <div className="segmented segmented--fill" role="group" aria-label="처리 방식">
            <button type="button" aria-pressed={action === 'reinterpret'} onClick={() => setAction('reinterpret')}>
              현장 정보 덧붙여 다시 해석
            </button>
            <button type="button" aria-pressed={action === 'manual'} onClick={() => setAction('manual')}>
              직접 입력
            </button>
          </div>

          {action === 'reinterpret' ? (
            <div className="field">
              <label htmlFor={contextId} className="field-label">
                덧붙일 내용
              </label>
              <textarea
                id={contextId}
                className="input"
                placeholder="예: 이 부재는 S1 소조립 보강재이고, 두 번째 글자는 B가 아니라 8이에요."
                value={context}
                onChange={(event) => setContext(event.target.value)}
              />
              <p className="field-hint">덧붙인 내용은 이 워크스페이스의 다음 해석에도 참고해요.</p>
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
          {done && <Notice>확인한 내용을 반영했어요.</Notice>}

          <p className="button-row">
            <button type="submit" className="btn btn--primary" disabled={submitting}>
              {submitting ? '보내는 중' : action === 'reinterpret' ? '다시 해석' : '해석 저장'}
            </button>
          </p>
        </form>
      </section>
    </>
  )
}
