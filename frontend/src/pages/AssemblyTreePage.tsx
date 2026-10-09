import { getAssemblyTree } from '../api/projects'
import { AssemblyTreeList } from '../components/AssemblyTreeList'
import { AsyncView } from '../components/AsyncView'
import { PageHeader } from '../components/PageHeader'
import { useAsync } from '../hooks/useAsync'
import { useProject } from '../hooks/useProject'
import { useWorkspace } from '../hooks/useWorkspace'
import { paths } from '../lib/paths'

/** 와이어프레임 3b — 조립 트리 (프로젝트(블록)별, 파인더 목록처럼 단계별 들여쓰기) */
export function AssemblyTreePage() {
  const workspace = useWorkspace()
  const project = useProject()
  const tree = useAsync((signal) => getAssemblyTree(workspace.id, project.id, signal), [workspace.id, project.id])

  return (
    <div className="page">
      <PageHeader
        breadcrumb={[{ label: project.name, to: paths.project(workspace.id, project.id) }, { label: '조립 트리' }]}
        title="조립 트리"
        description="블록에서 부재까지 조립 순서예요. 인식한 부재가 여기 있는지로 해석을 검증해요."
      />
      <AsyncView state={tree} isEmpty={(nodes) => nodes.length === 0} empty="이 블록에는 아직 조립 경로가 없어요. 도면에서 가져오는 기능은 준비 중이에요.">
        {(nodes) => <AssemblyTreeList nodes={nodes} />}
      </AsyncView>
    </div>
  )
}
