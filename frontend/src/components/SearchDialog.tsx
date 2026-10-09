import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { listJobs } from '../api/jobs'
import { useAsync } from '../hooks/useAsync'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { paths } from '../lib/paths'
import { ErrorNotice } from './Notice'
import styles from './SearchDialog.module.css'
import { StatusPill } from './StatusPill'

/** 검색 결과로 보여 줄 최대 개수 */
const MAX_RESULTS = 20

interface SearchDialogProps {
  workspaceId: string
  open: boolean
  onClose: () => void
}

/**
 * 검색 ⌘K 모달 (와이어프레임 2). 현재 워크스페이스의 작업을 검색한다.
 * 네이티브 <dialog> 의 showModal() 을 써서 포커스 가두기·Esc 닫기를 브라우저에 맡긴다.
 */
export function SearchDialog({ workspaceId, open, onClose }: SearchDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={dialogRef}
      className={styles.dialog}
      aria-label="작업 검색"
      onClose={onClose}
      // 패널 바깥(backdrop)을 누르면 닫는다. 패널이 dialog 를 꽉 채우므로 target 이 dialog 면 backdrop 이다.
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      {/* 열 때마다 검색어를 비우도록 열려 있을 때만 마운트 */}
      {open && <SearchPanel workspaceId={workspaceId} onNavigate={onClose} />}
    </dialog>
  )
}

interface SearchPanelProps {
  workspaceId: string
  onNavigate: () => void
}

function SearchPanel({ workspaceId, onNavigate }: SearchPanelProps) {
  const navigate = useNavigate()
  const inputId = useId()
  const resultsId = useId()
  const [query, setQuery] = useState('')
  const q = useDebouncedValue(query.trim(), 200)
  const results = useAsync((signal) => listJobs(workspaceId, { q: q || undefined }, signal), [workspaceId, q])
  const jobs = results.data?.slice(0, MAX_RESULTS)

  // Enter: 첫 번째 결과로 이동
  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    const first = jobs?.[0]
    if (!first) return
    navigate(paths.job(workspaceId, first.id))
    onNavigate()
  }

  return (
    <div className={styles.panel}>
      <form role="search" className={styles.searchRow} onSubmit={onSubmit}>
        <label htmlFor={inputId} className="visually-hidden">
          작업 검색
        </label>
        <input
          id={inputId}
          className={styles.input}
          type="search"
          placeholder="작업명, 조립 경로, 마킹 내용으로 검색"
          autoComplete="off"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-controls={resultsId}
        />
        <kbd className="kbd">Esc</kbd>
      </form>

      <section id={resultsId} className={styles.results} aria-live="polite" aria-busy={results.loading}>
        <h2 className={styles.groupTitle}>{q ? '검색 결과' : '최근 작업'}</h2>
        {results.error !== undefined ? (
          <ErrorNotice error={results.error} onRetry={results.reload} />
        ) : jobs === undefined ? (
          <p className={styles.hint}>불러오는 중…</p>
        ) : jobs.length === 0 ? (
          <p className={styles.hint}>{q ? `'${q}'에 해당하는 작업이 없습니다.` : '아직 작업이 없습니다.'}</p>
        ) : (
          <ul className={styles.list}>
            {jobs.map((job) => (
              <li key={job.id}>
                <Link className={styles.item} to={paths.job(workspaceId, job.id)} onClick={onNavigate}>
                  <span className={styles.itemName}>{job.name}</span>
                  <span className={styles.itemMeta}>{job.assembly_path ?? '조립 경로 없음'}</span>
                  <StatusPill status={job.status} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
