import { listWeldingStandards } from '../api/standards'
import { AsyncView } from '../components/AsyncView'
import { PageHeader } from '../components/PageHeader'
import { jointTypeLabel, positionLabel } from '../lib/labels'
import { useAsync } from '../hooks/useAsync'

/** 와이어프레임 3c — 표준 용접 기준 (모든 워크스페이스 공통, 읽기 전용) */
export function WeldingStandardsPage() {
  const standards = useAsync((signal) => listWeldingStandards(signal), [])

  return (
    <div className="page">
      <PageHeader
        title="용접 기준"
        description="모든 워크스페이스가 함께 쓰는 표준 기준표예요. 추천 조건은 이 표에서 고르고, 여기서는 고칠 수 없어요."
      />
      <AsyncView state={standards} isEmpty={(list) => list.length === 0} empty="아직 기준이 없어요.">
        {(list) => (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">이음 형태</th>
                  <th scope="col" className="num">
                    두께 (mm)
                  </th>
                  <th scope="col">공법</th>
                  <th scope="col">자세</th>
                  <th scope="col" className="num">
                    전류 (A)
                  </th>
                  <th scope="col" className="num">
                    전압 (V)
                  </th>
                  <th scope="col" className="num">
                    속도 (cm/min)
                  </th>
                </tr>
              </thead>
              <tbody>
                {list.map((standard) => (
                  <tr
                    key={`${standard.joint_type}-${standard.thickness_min_mm}-${standard.thickness_max_mm}-${standard.process}-${standard.position}`}
                  >
                    <td className="cell-title">
                      {jointTypeLabel(standard.joint_type)} <span className="secondary mono">{standard.joint_type}</span>
                    </td>
                    <td className="num nowrap">
                      {standard.thickness_min_mm}-{standard.thickness_max_mm}
                    </td>
                    <td>{standard.process}</td>
                    <td>{positionLabel(standard.position)}</td>
                    <td className="num">{standard.current_a}</td>
                    <td className="num">{standard.voltage_v}</td>
                    <td className="num">{standard.speed_cm_min}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </AsyncView>
    </div>
  )
}
