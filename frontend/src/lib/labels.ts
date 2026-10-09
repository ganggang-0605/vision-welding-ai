/** 계약 모델의 enum 값 → 화면 표시용 한국어 라벨 */
import type { AssemblyLevel, JobStatus, SymbolKind } from '../api/types'

/** 작업 진행 순서대로 */
export const JOB_STATUSES: readonly JobStatus[] = ['draft', 'analyzing', 'needs_review', 'awaiting_approval', 'approved']

export const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  draft: '초안',
  analyzing: '분석 중',
  needs_review: '확인 필요',
  awaiting_approval: '승인 대기',
  approved: '승인 완료',
}

/** 상태 표시(pill) 색 — index.css 의 .pill--* 와 짝 */
export type Tone = 'neutral' | 'info' | 'warning' | 'success'

export const JOB_STATUS_TONE: Record<JobStatus, Tone> = {
  draft: 'neutral',
  analyzing: 'neutral',
  needs_review: 'warning',
  awaiting_approval: 'info',
  approved: 'success',
}

/** 승인할 수 있는 상태 (그 외에는 백엔드가 409) */
export const APPROVABLE_STATUSES: readonly JobStatus[] = ['needs_review', 'awaiting_approval']

export const SYMBOL_KIND_LABEL: Record<SymbolKind, string> = {
  text: '문자',
  symbol: '기호',
}

/** 조립 트리 단계 — 위에서 아래 순서 (인덱스 = 들여쓰기 깊이) */
export const ASSEMBLY_LEVELS: readonly AssemblyLevel[] = ['BLOCK', 'LARGE', 'MID', 'SUB', 'PART']

export const ASSEMBLY_LEVEL_LABEL: Record<AssemblyLevel, string> = {
  BLOCK: '블록',
  LARGE: '대조립',
  MID: '중조립',
  SUB: '소조립',
  PART: '부재',
}
