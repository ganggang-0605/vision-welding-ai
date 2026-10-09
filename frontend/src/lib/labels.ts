/** 계약 모델의 enum 값 → 화면 표시용 한국어 라벨 */
import type {
  AssemblyLevel,
  Cell,
  CellFeature,
  JobStatus,
  LegLength,
  MemberRole,
  SymbolKind,
  WeldingCondition,
  Workspace,
} from '../api/types'

/** 워크스페이스 종류 한 줄: "개인" / "팀, 멤버 3명" */
export function workspaceKindLabel(workspace: Pick<Workspace, 'kind' | 'member_count'>): string {
  return workspace.kind === 'personal' ? '개인' : `팀, 멤버 ${workspace.member_count}명`
}

export const MEMBER_ROLE_LABEL: Record<MemberRole, string> = {
  owner: '소유자',
  member: '멤버',
}

/** 작업 진행 순서대로 */
export const JOB_STATUSES: readonly JobStatus[] = ['draft', 'analyzing', 'needs_review', 'awaiting_approval', 'approved']

export const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  draft: '해석 전',
  analyzing: '해석 중',
  needs_review: '확인 필요',
  awaiting_approval: '승인 대기',
  approved: '승인됨',
}

/** 작업자가 손을 대야 하는 상태. 화면에서 이 상태만 주황 글자로 강조한다. */
export const ATTENTION_STATUSES: readonly JobStatus[] = ['needs_review']

/** 아직 끝나지 않은 작업 (홈 제목 아래 '진행 중인 작업 N건') */
export const OPEN_STATUSES: readonly JobStatus[] = ['draft', 'analyzing', 'needs_review', 'awaiting_approval']

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

/** 용접 기준표의 이음 형태 코드 → 현장 용어. 모르는 코드는 그대로 보여 준다. */
const JOINT_TYPE_LABEL: Record<string, string> = {
  FILLET: '필렛',
  BUTT_V: 'V형 맞대기',
  BUTT_X: 'X형 맞대기',
  BUTT_I: 'I형 맞대기',
}

/** 용접 자세 코드 → 현장 용어 */
const POSITION_LABEL: Record<string, string> = {
  FLAT: '하향',
  HORIZONTAL: '수평',
  VERTICAL: '수직',
  OVERHEAD: '위보기',
  // AWS 자세 (용접 기준표 data/seed/welding_standards.csv)
  '1F': '아래보기 필렛',
  '2F': '수평 필렛',
  '3F': '수직 필렛',
  '4F': '위보기 필렛',
  '1G': '아래보기 맞대기',
  '2G': '수평 맞대기',
  '3G': '수직 맞대기',
  '4G': '위보기 맞대기',
}

export function jointTypeLabel(code: string): string {
  return JOINT_TYPE_LABEL[code] ?? code
}

export function positionLabel(code: string): string {
  return POSITION_LABEL[code] ?? code
}

/** 목록용 한 줄 요약: "필렛, FCAW, 하향" */
export function conditionSummary(condition: WeldingCondition): string {
  return [jointTypeLabel(condition.joint_type), condition.process, positionLabel(condition.position)].join(', ')
}

/** "220-260" 같은 범위 문자열에 단위를 붙인다. */
export function withUnit(range: string, unit: string): string {
  return range ? `${range} ${unit}` : range
}

/** 셀 형태 (현장에서 쓰는 영문 이름 그대로, 앞/뒤만 한국어) */
export const CELL_FEATURES: readonly CellFeature[] = ['slit', 'slot', 'collar_front', 'collar_back', 'scallop']

export const CELL_FEATURE_LABEL: Record<CellFeature, string> = {
  slit: 'Slit',
  slot: 'Slot',
  collar_front: '앞 Collar',
  collar_back: '뒤 Collar',
  scallop: 'Scallop',
}

/** 셀 한쪽: "앞 Collar + Scallop", 없으면 "없음" */
export function cellSideLabel(features: readonly CellFeature[]): string {
  return features.length ? features.map((feature) => CELL_FEATURE_LABEL[feature]).join(' + ') : '없음'
}

/** 목록용 한 줄: "좌 Slit, 우 앞 Collar + Scallop" */
export function cellSummary(cell: Cell): string {
  return `좌 ${cellSideLabel(cell.left)}, 우 ${cellSideLabel(cell.right)}`
}

/** 각장 한 줄: "F 5.5mm" */
export function legLengthLabel(leg: Pick<LegLength, 'code' | 'size_mm'>): string {
  return `${leg.code} ${leg.size_mm}mm`
}
