import type { LegLength } from '../api/types'
import styles from './LegLengthList.module.css'

/** 읽은 각장 표기 목록: 코드와 크기를 크게, 뜻과 원문을 작게. */
export function LegLengthList({ legs }: { legs: LegLength[] }) {
  return (
    <ul className="group">
      {legs.map((leg, index) => (
        <li key={`${leg.raw_text}-${index}`} className={styles.row}>
          <span className={styles.size}>
            <span className={styles.code}>{leg.code}</span>
            {leg.size_mm}
            <span className="stat-unit">mm</span>
          </span>
          <span className={styles.text}>
            <span>{leg.meaning ?? '사전에 없는 표기'}</span>
            <span className={styles.raw}>원문 {leg.raw_text}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}
