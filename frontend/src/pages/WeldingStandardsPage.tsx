import { listWeldingStandards } from '../api/standards'
import { AsyncView } from '../components/AsyncView'
import { PageHeader } from '../components/PageHeader'
import { useAsync } from '../hooks/useAsync'

/** 와이어프레임 3c — 표준 용접 기준 (모든 워크스페이스 공통, 읽기 전용) */
export function WeldingStandardsPage() {
  const standards = useAsync((signal) => listWeldingStandards(signal), [])

  return (
    <div className="page">
      <PageHeader
        title="용접 기준"
        eyebrow={<span className="badge">공통</span>}
        description="모든 워크스페이스가 함께 쓰는 공식 표준 용접 기준입니다(읽기 전용). 판별한 용접 조건이 이 기준과 충돌하는지 검증합니다."
      />
      <AsyncView state={standards} isEmpty={(list) => list.length === 0} empty="등록된 기준이 없습니다.">
        {(list) => (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">이음 형태</th>
                  <th scope="col" className="num">
                    두께 (mm)
                  </th>
                  <th scope="col">공정</th>
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
                    <td>{standard.joint_type}</td>
                    <td className="num nowrap">
                      {standard.thickness_min_mm}–{standard.thickness_max_mm}
                    </td>
                    <td>{standard.process}</td>
                    <td>{standard.position}</td>
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
