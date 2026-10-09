import { useId, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { createProject } from '../api/projects'
import { ErrorNotice } from '../components/Notice'
import { PageHeader } from '../components/PageHeader'
import { useWorkspaceContext } from '../hooks/useWorkspace'
import { paths } from '../lib/paths'

/** 새 프로젝트(호선). 만든 뒤 사이드바 목록을 다시 불러오고 그 프로젝트로 이동한다. */
export function NewProjectPage() {
  const { workspace, reloadProjects } = useWorkspaceContext()
  const navigate = useNavigate()
  const ids = { name: useId(), description: useId() }
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<unknown>()

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError(undefined)
    try {
      const project = await createProject(workspace.id, {
        name: name.trim(),
        description: description.trim() || null,
      })
      reloadProjects()
      navigate(paths.project(workspace.id, project.id))
    } catch (err) {
      setError(err)
      setSubmitting(false)
    }
  }

  return (
    <div className="page page--narrow">
      <PageHeader
        breadcrumb={[{ label: workspace.name, to: paths.workspaceHome(workspace.id) }, { label: '새 프로젝트' }]}
        title="새 프로젝트"
        description="호선 하나가 프로젝트 하나예요. 작업과 조립 트리는 호선별로 따로 관리하고, 문자·기호 사전은 워크스페이스 전체가 함께 써요."
      />

      <form className="form" onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor={ids.name} className="field-label">
            호선 이름
          </label>
          <input
            id={ids.name}
            className="input"
            required
            maxLength={100}
            placeholder="예: 3203호선"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor={ids.description} className="field-label">
            설명
          </label>
          <input
            id={ids.description}
            className="input"
            placeholder="선택. 예: 174K LNG 운반선"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>

        {error !== undefined && <ErrorNotice error={error} />}

        <p className="button-row">
          <button type="submit" className="btn btn--primary" disabled={submitting || !name.trim()}>
            {submitting ? '만드는 중' : '프로젝트 만들기'}
          </button>
          <Link className="btn btn--plain" to={paths.workspaceHome(workspace.id)}>
            취소
          </Link>
        </p>
      </form>
    </div>
  )
}
