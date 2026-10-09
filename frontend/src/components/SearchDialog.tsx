import { FileText, MagnifyingGlass } from '@phosphor-icons/react'
import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { listJobs } from '../api/jobs'
import type { Project } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { paths } from '../lib/paths'
import { ErrorNotice } from './Notice'
import styles from './SearchDialog.module.css'
import { StatusLabel } from './StatusLabel'

/** 검색 결과로 보여 줄 최대 개수 */
const MAX_RESULTS = 20

interface SearchDialogProps {
  workspaceId: string
  /** 결과에 블록 이름을 붙이는 데 쓴다. */
  projects: Project[]
  open: boolean
  onClose: () => void
}

/**
 * 검색 ⌘K 모달 (와이어프레임 2, 맥 Spotlight 모양). 현재 워크스페이스의 모든 프로젝트에서 작업을 검색한다.
 * 네이티브 <dialog> 의 showModal() 을 써서 포커스 가두기·Esc 닫기를 브라우저에 맡긴다.
 */
export function SearchDialog({ workspaceId, projects, open, onClose }: SearchDialogProps) {
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
      {open && <SearchPanel workspaceId={workspaceId} projects={projects} onNavigate={onClose} />}
    </dialog>
  )
}

interface SearchPanelProps {
  workspaceId: string
  projects: Project[]
  onNavigate: () => void
}

function SearchPanel({ workspaceId, projects, onNavigate }: SearchPanelProps) {
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
    navigate(paths.job(workspaceId, first.project_id, first.id))
    onNavigate()
  }

  return (
    <div className={styles.panel}>
      <form role="search" className={styles.searchRow} onSubmit={onSubmit}>
        <label htmlFor={inputId} className="visually-hidden">
          작업 검색
        </label>
        <MagnifyingGlass className={styles.searchIcon} size={22} aria-hidden="true" />
        <input
          id={inputId}
          className={styles.input}
          type="search"
          placeholder="작업 이름, 조립 경로, 표기 내용"
          autoComplete="off"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-controls={resultsId}
        />
        <kbd className="kbd">esc</kbd>
      </form>

      <section id={resultsId} className={styles.results} aria-live="polite" aria-busy={results.loading}>
        <h2 className={styles.groupTitle}>{q ? '작업' : '최근 작업'}</h2>
        {results.error !== undefined ? (
          <ErrorNotice error={results.error} onRetry={results.reload} />
        ) : jobs === undefined ? (
          <p className={styles.hint}>찾는 중</p>
        ) : jobs.length === 0 ? (
          <p className={styles.hint}>{q ? `'${q}'와 맞는 작업이 없어요.` : '아직 작업이 없어요.'}</p>
        ) : (
          <ul className={styles.list}>
            {jobs.map((job, index) => (
              <li key={job.id}>
                <Link
                  className={styles.item}
                  to={paths.job(workspaceId, job.project_id, job.id)}
                  onClick={onNavigate}
                  // Enter 로 열리는 첫 결과를 미리 강조한다 (Spotlight 와 같은 동작).
                  data-default={index === 0 || undefined}
                >
                  <span className={styles.itemIcon} aria-hidden="true">
                    <FileText size={17} />
                  </span>
                  <span className={styles.itemText}>
                    <span className={styles.itemName}>{job.name}</span>
                    <span className={styles.itemMeta}>
                      {projects.find((project) => project.id === job.project_id)?.name}
                      {job.assembly_path && <span className={styles.metaPath}>{job.assembly_path}</span>}
                    </span>
                  </span>
                  <StatusLabel status={job.status} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
