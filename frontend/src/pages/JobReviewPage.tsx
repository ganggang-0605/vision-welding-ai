import { Plus, Trash, WarningCircle } from '@phosphor-icons/react'
import { useId, useState, type FormEvent } from 'react'
import { reviewJob } from '../api/jobs'
import type { Cell, CellFeature, Job, LegLength, ReviewAction, ReviewRequest, WeldingCondition } from '../api/types'
import { JobFrame } from '../components/JobFrame'
import { ErrorNotice, Notice } from '../components/Notice'
import { useWorkspace } from '../hooks/useWorkspace'
import { CELL_FEATURE_LABEL, CELL_FEATURES } from '../lib/labels'
import styles from './JobReviewPage.module.css'

const CONDITION_FIELDS: { key: keyof WeldingCondition; label: string }[] = [
  { key: 'joint_type', label: '이음 형태' },
  { key: 'process', label: '공법' },
  { key: 'position', label: '자세' },
  { key: 'current_a', label: '전류 (A)' },
  { key: 'voltage_v', label: '전압 (V)' },
  { key: 'speed_cm_min', label: '속도 (cm/min)' },
]

/** 데모 사전의 각장 코드. 사전에 다른 코드가 있으면 직접 입력할 수 있게 목록 밖 값도 그대로 둔다. */
const LEG_CODES = ['F', 'V', 'S']

const EMPTY_CELL: Cell = { left: [], right: [] }

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
  const [cell, setCell] = useState<Cell>(job.cell ?? EMPTY_CELL)
  // 크기는 입력 중 '5.' 같은 값도 받도록 문자열로 들고 있다가 보낼 때 숫자로 바꾼다.
  const [legs, setLegs] = useState(job.leg_lengths.map((leg) => ({ code: leg.code, size: String(leg.size_mm) })))
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<unknown>()
  const [done, setDone] = useState(false)

  /** 직접 입력에서 처음 값과 달라진 것만 (빈 값은 보내지 않는다) */
  const changedValues = (): Record<string, unknown> => {
    const values: Record<string, unknown> = {}
    const nextInterpretation = interpretation.trim()
    if (nextInterpretation && nextInterpretation !== (job.marking?.interpretation ?? '')) {
      values.interpretation = nextInterpretation
    }
    const conditionFilled = CONDITION_FIELDS.every(({ key }) => condition[key].trim())
    if (conditionFilled && !sameJson(condition, job.welding_condition ?? EMPTY_CONDITION)) {
      values.welding_condition = condition
    }
    if (!sameJson(cell, job.cell ?? EMPTY_CELL)) values.cell = cell
    const nextLegs = legs
      .filter((leg) => leg.code && Number(leg.size) > 0)
      .map((leg): Omit<LegLength, 'meaning'> => ({
        code: leg.code,
        size_mm: Number(leg.size),
        raw_text: `${leg.code}${leg.size}`,
      }))
    const before = job.leg_lengths.map((leg) => [leg.code, leg.size_mm])
    if (!sameJson(nextLegs.map((leg) => [leg.code, leg.size_mm]), before)) values.leg_lengths = nextLegs
    return values
  }

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    // manual 은 바꾼 값만 보낸다 (키 = 고칠 대상, shared/schemas/analysis.schema.json 의 Correction).
    // 해석은 백그라운드에서 돌고, JobFrame 이 analyzing 동안 작업을 다시 읽어 결과를 보여 준다.
    const values = action === 'manual' ? changedValues() : {}
    if (action === 'manual' && Object.keys(values).length === 0) {
      setError(new Error('바꾼 값이 없어요.'))
      return
    }
    const body: ReviewRequest =
      action === 'reinterpret' ? { action, context: context.trim() || null } : { action, values }
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
                <legend className="field-label">셀 형태</legend>
                <CellSideToggles
                  side="좌"
                  value={cell.left}
                  onChange={(left) => setCell({ ...cell, left })}
                />
                <CellSideToggles
                  side="우"
                  value={cell.right}
                  onChange={(right) => setCell({ ...cell, right })}
                />
                <p className="field-hint">한쪽에 여러 개를 고를 수 있어요 (예: 앞 Collar + Scallop).</p>
              </fieldset>
              <fieldset className="field">
                <legend className="field-label">각장</legend>
                {legs.map((leg, index) => (
                  <div key={index} className={styles.legRow}>
                    <select
                      className="input"
                      aria-label={`${index + 1}번째 각장 코드`}
                      value={leg.code}
                      onChange={(event) =>
                        setLegs(legs.map((item, i) => (i === index ? { ...item, code: event.target.value } : item)))
                      }
                    >
                      {[...new Set([...LEG_CODES, leg.code])].map((code) => (
                        <option key={code} value={code}>
                          {code}
                        </option>
                      ))}
                    </select>
                    <input
                      className="input"
                      inputMode="decimal"
                      aria-label={`${index + 1}번째 각장 크기 (mm)`}
                      placeholder="5.5"
                      value={leg.size}
                      onChange={(event) =>
                        setLegs(legs.map((item, i) => (i === index ? { ...item, size: event.target.value } : item)))
                      }
                    />
                    <span className="secondary">mm</span>
                    <button
                      type="button"
                      className="icon-btn icon-btn--danger"
                      onClick={() => setLegs(legs.filter((_, i) => i !== index))}
                      title="지우기"
                    >
                      <Trash size={16} aria-hidden="true" />
                      <span className="visually-hidden">{index + 1}번째 각장 지우기</span>
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className={`btn btn--plain ${styles.addLeg}`}
                  onClick={() => setLegs([...legs, { code: 'F', size: '' }])}
                >
                  <Plus size={14} weight="bold" aria-hidden="true" />
                  각장 추가
                </button>
              </fieldset>
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
          {done && <Notice>확인한 내용으로 다시 해석하고 있어요. 끝나면 위 항목이 바뀌어요.</Notice>}

          <p className="button-row">
            <button type="submit" className="btn btn--primary" disabled={submitting || job.status === 'analyzing'}>
              {submitting ? '보내는 중' : action === 'reinterpret' ? '다시 해석' : '해석 저장'}
            </button>
          </p>
        </form>
      </section>
    </>
  )
}

interface CellSideTogglesProps {
  side: string
  value: CellFeature[]
  onChange: (value: CellFeature[]) => void
}

/** 셀 한쪽의 형태를 켜고 끄는 버튼 묶음 (여러 개 선택) */
function CellSideToggles({ side, value, onChange }: CellSideTogglesProps) {
  const toggle = (feature: CellFeature) =>
    onChange(
      value.includes(feature)
        ? value.filter((item) => item !== feature)
        : CELL_FEATURES.filter((item) => item === feature || value.includes(item)),
    )
  return (
    <div className={styles.cellSide} role="group" aria-label={`셀 ${side}쪽 형태`}>
      <span className={styles.cellSideLabel}>{side}</span>
      <span className="chips">
        {CELL_FEATURES.map((feature) => (
          <button
            key={feature}
            type="button"
            className="chip"
            aria-pressed={value.includes(feature)}
            onClick={() => toggle(feature)}
          >
            {CELL_FEATURE_LABEL[feature]}
          </button>
        ))}
      </span>
    </div>
  )
}

function sameJson(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}
