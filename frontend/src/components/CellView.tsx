import type { Cell, CellFeature } from '../api/types'
import { CELL_FEATURE_LABEL } from '../lib/labels'
import styles from './CellView.module.css'

/** 셀 좌·우 끝의 형태를 두 칸으로 보여 준다. 한쪽에 여러 형태가 겹치면 줄을 바꿔 + 로 잇는다. */
export function CellView({ cell }: { cell: Cell }) {
  return (
    <dl className={styles.cell}>
      <Side label="좌" features={cell.left} />
      <Side label="우" features={cell.right} />
    </dl>
  )
}

function Side({ label, features }: { label: string; features: CellFeature[] }) {
  return (
    <div className={styles.side}>
      <dt className={styles.label}>{label}</dt>
      <dd className={styles.features}>
        {features.length === 0 ? (
          <span className={styles.none}>없음</span>
        ) : (
          features.map((feature, index) => (
            <span key={feature} className={styles.feature}>
              {index > 0 && <span className={styles.plus}>+ </span>}
              {CELL_FEATURE_LABEL[feature]}
            </span>
          ))
        )}
      </dd>
    </div>
  )
}
