import { ArrowClockwise, ImageSquare, Plus } from '@phosphor-icons/react'
import { useId, useState } from 'react'
import { analyzeJob, jobImageUrl, listAnalyses, listJobImages, uploadJobImage } from '../api/jobs'
import type { Analysis, Job } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { ErrorNotice } from './Notice'
import styles from './JobPhotos.module.css'
import { PhotoAnnotations } from './PhotoAnnotations'

interface JobPhotosProps {
  workspaceId: string
  job: Job
  /** 사진을 해석해 작업이 바뀌었을 때 (JobFrame 이 작업을 다시 불러온다) */
  onAnalyzed: () => void
}

/**
 * 작업의 사진과 해석 위치. 사진 올리기 → 해석(1·2·3단계) → 다시 해석을 여기서 한다.
 * 사진이 여러 장이면 아래 미리보기로 고르고, 고른 사진의 가장 최근 해석 결과를 박스로 보여 준다.
 */
export function JobPhotos({ workspaceId, job, onAnalyzed }: JobPhotosProps) {
  const inputId = useId()
  // 작업이 다시 해석되면(상태·해석 문장이 바뀌면) 사진·해석 결과도 다시 불러온다.
  const version = `${job.status}|${job.marking?.raw_text ?? ''}|${job.marking?.interpretation ?? ''}`
  const images = useAsync((signal) => listJobImages(workspaceId, job.id, signal), [workspaceId, job.id, version])
  const analyses = useAsync((signal) => listAnalyses(workspaceId, job.id, signal), [workspaceId, job.id, version])
  const [selectedId, setSelectedId] = useState<string>()
  const [busy, setBusy] = useState<'upload' | 'analyze'>()
  const [error, setError] = useState<unknown>()

  const list = images.data ?? []
  const latestAnalysis = analyses.data?.at(-1)
  // 고른 사진 → 없으면 가장 최근에 해석한 사진 → 없으면 가장 최근 사진
  const current =
    list.find((image) => image.image_id === selectedId) ??
    list.find((image) => image.image_id === latestAnalysis?.image_id) ??
    list.at(-1)
  const analysisOf = (imageId: string): Analysis | undefined =>
    analyses.data?.filter((analysis) => analysis.image_id === imageId).at(-1)
  const analyzed = current ? analysisOf(current.image_id) !== undefined : false

  const run = async (work: () => Promise<unknown>, kind: 'upload' | 'analyze') => {
    setBusy(kind)
    setError(undefined)
    try {
      await work()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(undefined)
    }
  }

  const upload = (file: File) =>
    run(async () => {
      const image = await uploadJobImage(workspaceId, job.id, file)
      setSelectedId(image.image_id)
      images.reload()
    }, 'upload')

  const analyze = () =>
    run(async () => {
      await analyzeJob(workspaceId, job.id, current ? { image_id: current.image_id } : {})
      onAnalyzed()
    }, 'analyze')

  return (
    <section className={styles.section} aria-labelledby="photos-title">
      <div className="section-head">
        <h2 id="photos-title" className="section-title">
          사진
        </h2>
        <div className="button-row">
          <label htmlFor={inputId} className="btn" aria-disabled={busy !== undefined}>
            <Plus size={14} weight="bold" aria-hidden="true" />
            {busy === 'upload' ? '올리는 중' : '사진 추가'}
          </label>
          <input
            id={inputId}
            className="visually-hidden"
            type="file"
            accept="image/*"
            capture="environment"
            disabled={busy !== undefined}
            onChange={(event) => {
              const file = event.target.files?.[0]
              event.target.value = ''
              if (file) void upload(file)
            }}
          />
          {current && (
            <button type="button" className="btn btn--primary" onClick={analyze} disabled={busy !== undefined}>
              {analyzed && <ArrowClockwise size={14} weight="bold" aria-hidden="true" />}
              {busy === 'analyze' ? '해석하는 중' : analyzed ? '다시 해석' : '해석 시작'}
            </button>
          )}
        </div>
      </div>

      {error !== undefined && <ErrorNotice error={error} />}

      {images.error !== undefined ? (
        <ErrorNotice error={images.error} onRetry={images.reload} />
      ) : images.data === undefined ? (
        <div className={styles.placeholder} aria-label="불러오는 중" />
      ) : current ? (
        <>
          <PhotoAnnotations
            key={current.image_id}
            src={jobImageUrl(workspaceId, job.id, current.image_id)}
            image={current}
            analysis={analysisOf(current.image_id)}
          />
          {list.length > 1 && (
            <ul className={styles.thumbs} aria-label="사진 고르기">
              {list.map((image, index) => (
                <li key={image.image_id}>
                  <button
                    type="button"
                    className={styles.thumb}
                    aria-pressed={image.image_id === current.image_id}
                    onClick={() => setSelectedId(image.image_id)}
                  >
                    <img src={jobImageUrl(workspaceId, job.id, image.image_id)} alt={`${index + 1}번째 사진`} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <label htmlFor={inputId} className={styles.empty}>
          <ImageSquare size={28} aria-hidden="true" />
          표기가 보이게 셀 사진을 찍거나 골라 주세요
        </label>
      )}
    </section>
  )
}
