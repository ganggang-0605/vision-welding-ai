import { useId, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { analyzeJob, createJob, uploadJobImage } from '../api/jobs'
import type { Job } from '../api/types'
import { getAssemblyTree } from '../api/workspaces'
import { ErrorNotice, Notice } from '../components/Notice'
import { PageHeader } from '../components/PageHeader'
import { useAsync } from '../hooks/useAsync'
import { useObjectUrl } from '../hooks/useObjectUrl'
import { useWorkspace } from '../hooks/useWorkspace'
import { paths } from '../lib/paths'

/** 작업은 만들었지만 사진 업로드·분석 단계에서 멈춘 경우 */
interface PartialResult {
  job: Job
  error: unknown
}

/**
 * 와이어프레임 4 — 현장 촬영(모바일) = 새 작업.
 * 작업 생성 → (사진이 있으면) 업로드 → 분석 순서로 호출한다. 업로드·분석은 파이프라인 구현 전까지 501.
 */
export function NewJobPage() {
  const workspace = useWorkspace()
  const navigate = useNavigate()
  const ids = { photo: useId(), photoHint: useId(), name: useId(), path: useId(), pathList: useId() }

  // 조립 경로 입력 자동완성용 (부재 단계만)
  const tree = useAsync((signal) => getAssemblyTree(workspace.id, signal), [workspace.id])
  const partPaths = tree.data?.filter((node) => node.level === 'PART').map((node) => node.path) ?? []

  const [name, setName] = useState('')
  const [assemblyPath, setAssemblyPath] = useState('')
  const [photo, setPhoto] = useState<File>()
  const [previewUrl, setPreviewBlob] = useObjectUrl()
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
      job = await createJob(workspace.id, { name: name.trim(), assembly_path: assemblyPath.trim() || null })
    } catch (err) {
      setError(err)
      setSubmitting(false)
      return
    }

    try {
      if (photo) {
        await uploadJobImage(workspace.id, job.id, photo)
        await analyzeJob(workspace.id, job.id)
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
        <PageHeader title="새 작업" description="작업을 만들었지만 사진 분석까지는 진행하지 못했습니다." />
        <Notice tone="info">작업 ‘{partial.job.name}’을(를) 만들었습니다.</Notice>
        <ErrorNotice error={partial.error} />
        <p className="button-row">
          <Link className="btn btn--primary" to={paths.job(workspace.id, partial.job.id)}>
            작업 보기
          </Link>
          <Link className="btn" to={paths.workspaceHome(workspace.id)}>
            작업 DB로
          </Link>
        </p>
      </div>
    )
  }

  return (
    <div className="page page--narrow">
      <PageHeader
        title="새 작업"
        description="현장에서 부재 마킹을 촬영해 작업을 만듭니다. 휴대폰에서는 카메라가 바로 열립니다."
      />

      <form className="form" onSubmit={onSubmit}>
        <div className="field">
          <span id={ids.photo} className="field-label">
            마킹 사진
          </span>
          <label className="capture">
            {previewUrl ? (
              <img className="capture-preview" src={previewUrl} alt="선택한 마킹 사진 미리보기" />
            ) : (
              <span>사진 촬영 또는 선택</span>
            )}
            <input
              className="visually-hidden"
              type="file"
              accept="image/*"
              capture="environment"
              aria-labelledby={ids.photo}
              aria-describedby={ids.photoHint}
              onChange={(event) => {
                const file = event.target.files?.[0]
                setPhoto(file)
                setPreviewBlob(file)
              }}
            />
          </label>
          <p id={ids.photoHint} className="field-hint">{photo ? photo.name : '마킹이 화면 가운데 오도록, 반사가 적은 각도로 찍어 주세요.'}</p>
        </div>

        <div className="field">
          <label htmlFor={ids.name} className="field-label">
            작업명
          </label>
          <input
            id={ids.name}
            className="input"
            required
            placeholder="예: A1-P1 부재 표기"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor={ids.path} className="field-label">
            조립 경로 (선택)
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
          <p className="field-hint">조립 트리의 부재 경로입니다. 비워 두면 분석 결과로 채웁니다.</p>
        </div>

        {error !== undefined && <ErrorNotice error={error} />}

        <p className="button-row">
          <button type="submit" className="btn btn--primary" disabled={submitting || !name.trim()}>
            {submitting ? '처리 중…' : photo ? '작업 만들고 분석' : '작업 만들기'}
          </button>
          <Link className="btn" to={paths.workspaceHome(workspace.id)}>
            취소
          </Link>
        </p>
      </form>
    </div>
  )
}
