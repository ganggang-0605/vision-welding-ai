import { Check } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import type { AnalysisStage, Job } from '../api/types'
import styles from './AnalysisProgress.module.css'

/**
 * 단계와 보통 걸리는 시간(초). 막대에서 각 단계가 차지하는 길이도 이 비율 — 실제로 오래 걸리는 2단계(VLM)가 길다.
 * VLM 을 끄면 2단계가 금방 끝나서 막대가 바로 넘어간다.
 */
const STAGES: { key: AnalysisStage; label: string; seconds: number }[] = [
  { key: 'vision', label: '시각 인식', seconds: 6 },
  { key: 'context', label: '맥락 해석 (DB · VLM)', seconds: 20 },
  { key: 'confidence', label: '신뢰도 산출', seconds: 2 },
]
const TOTAL = STAGES.reduce((sum, stage) => sum + stage.seconds, 0)
/** 한 단계 안에서는 시간이 지날수록 천천히 차오르다 이 비율에서 멈춘다 (다음 단계로 넘어가야 채워짐) */
const STAGE_CAP = 0.92
const TICK_MS = 200

/** 해석 중(analyzing) 진행 막대 — 백엔드가 알려 주는 지금 단계(analysis_stage)와 그 단계에서 지난 시간으로 그린다. */
export function AnalysisProgress({ job }: { job: Job }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), TICK_MS)
    return () => clearInterval(timer)
  }, [])

  const index = Math.max(0, STAGES.findIndex((stage) => stage.key === job.analysis_stage))
  const current = STAGES[index]
  const elapsed = job.analysis_stage_at ? Math.max(0, (now - Date.parse(job.analysis_stage_at)) / 1000) : 0
  const within = STAGE_CAP * (1 - Math.exp(-elapsed / current.seconds))
  const before = STAGES.slice(0, index).reduce((sum, stage) => sum + stage.seconds, 0)
  const percent = Math.round(((before + within * current.seconds) / TOTAL) * 100)

  return (
    <div className={styles.progress}>
      <div className={styles.head}>
        <p className={styles.title}>해석하고 있어요</p>
        <p className={styles.hint}>사진 한 장에 10~30초쯤 걸려요</p>
      </div>
      <div
        className={styles.track}
        role="progressbar"
        aria-label="해석 진행"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-valuetext={`${index + 1}단계 ${current.label} 중`}
      >
        <div className={styles.bar} style={{ width: `${percent}%` }} />
      </div>
      <ol className={styles.steps}>
        {STAGES.map((stage, i) => (
          <li key={stage.key} className={styles.step} data-state={i < index ? 'done' : i === index ? 'current' : 'todo'}>
            {i < index ? <Check size={14} weight="bold" aria-hidden="true" /> : <span className={styles.number}>{i + 1}</span>}
            {stage.label}
          </li>
        ))}
      </ol>
    </div>
  )
}
