import { Camera, Plus, X } from '@phosphor-icons/react'
import { useId, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { analyzeJob, createJob, uploadJobImage } from '../api/jobs'
import type { Job } from '../api/types'
import { getWorkspaceAssemblyTree } from '../api/workspaces'
import { ErrorNotice, Notice } from '../components/Notice'
import { PageHeader } from '../components/PageHeader'
import { useAsync } from '../hooks/useAsync'
import { usePreviewFiles } from '../hooks/useObjectUrl'
import { useWorkspace } from '../hooks/useWorkspace'
import { paths } from '../lib/paths'
import styles from './NewJobPage.module.css'

/** 작업은 만들었지만 사진 업로드·분석 단계에서 멈춘 경우 */
interface PartialResult {
  job: Job
  error: unknown
}

/**
 * 와이어프레임 4 — 현장 촬영(모바일) = 새 작업.
 * 작업 생성 → (사진이 있으면) 사진을 모두 업로드 → 모두 해석(올린 순서, 작업에는 마지막 사진의 결과) 순서로 호출한다.
 */
export function NewJobPage() {
  const workspace = useWorkspace()
  const navigate = useNavigate()
  const ids = { photo: useId(), photoHint: useId(), name: useId(), path: useId(), pathList: useId() }

  // 조립 경로 입력 자동완성용 (워크스페이스 조립 경로 사전의 부재 단계만)
  const tree = useAsync((signal) => getWorkspaceAssemblyTree(workspace.id, signal), [workspace.id])
  const partPaths = tree.data?.filter((node) => node.level === 'PART').map((node) => node.path) ?? []

  const [name, setName] = useState('')
  const [assemblyPath, setAssemblyPath] = useState('')
  const [photos, addPhotos, removePhoto] = usePreviewFiles()
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<unknown>()
  const [partial, setPartial] = useState<PartialResult>()

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError(undefined)

    let job: Job
    try {
      // TODO: 같은 워크스페이스의 과거 작업 연결 (related_job_ids) 선택 UI
      job = await createJob(workspace.id, {
        name: name.trim(),
        assembly_path: assemblyPath.trim() || null,
      })
    } catch (err) {
      setError(err)
      setSubmitting(false)
      return
    }

    try {
      if (photos.length > 0) {
        const imageIds: string[] = []
        for (const { file } of photos) imageIds.push((await uploadJobImage(workspace.id, job.id, file)).image_id)
        await analyzeJob(workspace.id, job.id, { image_ids: imageIds })
      }
      navigate(paths.job(workspace.id, job.id))
    } catch (err) {
      // 작업 자체는 만들어졌으므로 결과 화면으로 갈 수 있게 안내한다.
      setPartial({ job, error: err })
      setSubmitting(false)
    }
  }

  if (partial) {
    return (
      <div className="page page--narrow">
        <PageHeader
          breadcrumb={[{ label: '작업', to: paths.workspaceHome(workspace.id) }, { label: '새 작업' }]}
          title="새 작업"
          description="작업은 만들었지만 사진 해석까지는 하지 못했어요."
        />
        <Notice title={partial.job.name}>작업을 만들었어요. 사진은 작업 화면에서 다시 올릴 수 있어요.</Notice>
        <ErrorNotice error={partial.error} />
        <p className="button-row">
          <Link className="btn btn--primary" to={paths.job(workspace.id, partial.job.id)}>
            작업 보기
          </Link>
          <Link className="btn btn--plain" to={paths.workspaceHome(workspace.id)}>
            작업 목록으로
          </Link>
        </p>
      </div>
    )
  }

  return (
    <div className="page page--narrow">
      <PageHeader
        breadcrumb={[{ label: '작업', to: paths.workspaceHome(workspace.id) }, { label: '새 작업' }]}
        title="새 작업"
        description="부재 표기를 찍으면 작업이 만들어지고 바로 해석해요."
      />

      <form className="form" onSubmit={onSubmit}>
        <div className="field">
          <span id={ids.photo} className="field-label">
            표기 사진
          </span>
          {photos.length > 0 && (
            <ul className={styles.thumbs} aria-label="고른 사진">
              {photos.map(({ url }, index) => (
                <li key={url} className={styles.thumb}>
                  <img src={url} alt={`고른 사진 ${index + 1}`} />
                  <button
                    type="button"
                    className={styles.remove}
                    onClick={() => removePhoto(index)}
                    title="빼기"
                  >
                    <X size={14} weight="bold" aria-hidden="true" />
                    <span className="visually-hidden">{index + 1}번째 사진 빼기</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <label className={photos.length > 0 ? `${styles.capture} ${styles.captureMore}` : styles.capture}>
            <span className={styles.prompt}>
              {photos.length > 0 ? <Plus size={22} aria-hidden="true" /> : <Camera size={30} aria-hidden="true" />}
              {photos.length > 0 ? '사진 더 고르기' : '사진 찍기 또는 고르기 (여러 장 가능)'}
            </span>
            <input
              className="visually-hidden"
              type="file"
              accept="image/*"
              multiple
              aria-labelledby={ids.photo}
              aria-describedby={ids.photoHint}
              onChange={(event) => {
                addPhotos(Array.from(event.target.files ?? []))
                event.target.value = '' // 같은 사진을 빼고 다시 고를 수 있게
              }}
            />
          </label>
          <p id={ids.photoHint} className="field-hint">
            {photos.length > 0
              ? `${photos.length}장 — 올린 순서대로 모두 해석하고, 작업 결과에는 마지막 사진을 보여 줘요.`
              : '표기가 가운데 오도록, 빛 반사가 적은 각도에서 찍어 주세요.'}
          </p>
        </div>

        <div className="field">
          <label htmlFor={ids.name} className="field-label">
            작업 이름
          </label>
          <input
            id={ids.name}
            className="input"
            required
            placeholder="예: S1 블록"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor={ids.path} className="field-label">
            조립 경로
          </label>
          <input
            id={ids.path}
            className="input mono"
            list={ids.pathList}
            placeholder="예: A1/L1/M2/S1/P-1"
            value={assemblyPath}
            onChange={(event) => setAssemblyPath(event.target.value)}
          />
          <datalist id={ids.pathList}>
            {partPaths.map((path) => (
              <option key={path} value={path} />
            ))}
          </datalist>
          <p className="field-hint">비워 두면 해석 결과로 찾아 채워요.</p>
        </div>

        {error !== undefined && <ErrorNotice error={error} />}

        <p className="button-row">
          <button type="submit" className="btn btn--primary" disabled={submitting || !name.trim()}>
            {submitting ? '만드는 중' : photos.length > 0 ? '해석 시작' : '작업 만들기'}
          </button>
          <Link className="btn btn--plain" to={paths.workspaceHome(workspace.id)}>
            취소
          </Link>
        </p>
      </form>
    </div>
  )
}
