/**
 * 백엔드 API 계약(contract) 모델.
 * 필드명은 백엔드 JSON 그대로 snake_case, id 는 모두 문자열이다. 계약이 바뀌면 이 파일부터 고친다.
 */

/** ISO 8601 날짜·시간 문자열 (예: "2026-10-09T03:00:00Z") */
export type DateTimeString = string

// ── 워크스페이스 ──────────────────────────────────────────────

/** 최상위 단위 (조선소·공정 하나). 작업·문자/기호 사전·조립 트리가 워크스페이스에 속한다. */
export interface Workspace {
  id: string
  name: string
  description: string | null
  created_at: DateTimeString
}

/** 새 워크스페이스의 문자/기호 사전 시작 방식 */
export type DictionarySource = 'empty' | 'copy'

export interface WorkspaceCreate {
  /** 1~100자 */
  name: string
  description?: string | null
  /** 기본값 'empty'. 'copy' 면 copy_from_workspace_id 의 사전을 복제한다. */
  dictionary_source?: DictionarySource
  copy_from_workspace_id?: string | null
}

// ── 문자/기호 사전 (워크스페이스별) ───────────────────────────

export type SymbolKind = 'text' | 'symbol'

export interface SymbolEntry {
  id: string
  code: string
  kind: SymbolKind
  meaning: string
  aliases: string[]
  welding_joint_type: string | null
}

export interface SymbolEntryCreate {
  code: string
  kind: SymbolKind
  meaning: string
  /** 기본값 [] */
  aliases?: string[]
  welding_joint_type?: string | null
}

/** PATCH 본문. 보낸 필드만 수정된다. */
export interface SymbolEntryUpdate {
  code?: string
  kind?: SymbolKind
  meaning?: string
  aliases?: string[]
  welding_joint_type?: string | null
}

// ── 조립 트리 (워크스페이스별) ────────────────────────────────

/** 블록 → 대조립 → 중조립 → 소조립 → 부재 */
export type AssemblyLevel = 'BLOCK' | 'LARGE' | 'MID' | 'SUB' | 'PART'

export interface AssemblyNode {
  node_id: string
  parent_id: string | null
  level: AssemblyLevel
  /** 예: "A1/L1/M2/S1/P-1" */
  path: string
}

// ── 작업 ──────────────────────────────────────────────────────

export type JobStatus = 'draft' | 'analyzing' | 'needs_review' | 'awaiting_approval' | 'approved'

/** 부재 표기 인식·해석 결과 */
export interface Marking {
  raw_text: string
  symbols: string[]
  interpretation: string
}

/** 용접 조건. 값은 범위 문자열 (예: current_a "220-260") */
export interface WeldingCondition {
  joint_type: string
  process: string
  position: string
  current_a: string
  voltage_v: string
  speed_cm_min: string
}

/** 다계층 신뢰도 (0~100) */
export interface Confidence {
  visual: number
  db_consistency: number
  vlm_reasoning: number
  overall: number
}

export interface Job {
  id: string
  workspace_id: string
  name: string
  status: JobStatus
  assembly_path: string | null
  related_job_ids: string[]
  created_at: DateTimeString
  approved_at: DateTimeString | null
  approved_by: string | null
  marking: Marking | null
  welding_condition: WeldingCondition | null
  confidence: Confidence | null
  evidence: string[]
  needs_review: string[]
}

export interface JobCreate {
  name: string
  assembly_path?: string | null
  /** 같은 워크스페이스의 과거 작업 id (없는 id 면 422). 기본값 [] */
  related_job_ids?: string[]
}

/** GET /workspaces/{id}/jobs 쿼리 */
export interface JobListParams {
  /** 작업명·조립 경로·마킹 원문/해석에서 대소문자 구분 없이 검색 */
  q?: string
  /** 빈 값·생략이면 전체 */
  status?: JobStatus
}

export type ReviewAction = 'reinterpret' | 'manual'

export interface ReviewRequest {
  /** 'reinterpret': 맥락을 추가해 재해석, 'manual': 작업자가 직접 해석 */
  action: ReviewAction
  context?: string | null
  values?: Record<string, unknown> | null
}

export interface ApproveRequest {
  approved_by: string
}

// ── 표준 용접 기준 (전체 공통, 읽기 전용) ─────────────────────

export interface WeldingStandard {
  joint_type: string
  thickness_min_mm: number
  thickness_max_mm: number
  process: string
  position: string
  current_a: string
  voltage_v: string
  speed_cm_min: string
}

// ── 로봇 연계 JSON (schemas/robot_output.schema.json) ─────────

/** 승인된 작업만 내보낸다. 스키마 파일과 같이 모든 필드 필수 (중첩 객체 포함). */
export interface RobotOutput {
  job_id: string
  workspace_id: string
  created_at: DateTimeString
  assembly_path: string
  marking: Marking
  welding_condition: WeldingCondition
  confidence: Confidence
  evidence: string[]
  needs_review: string[]
  approved: boolean
  approved_by: string
}
