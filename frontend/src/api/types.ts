/**
 * 백엔드 API 계약(contract) 모델.
 * 필드명은 백엔드 JSON 그대로 snake_case, id 는 모두 문자열이다. 계약이 바뀌면 이 파일부터 고친다.
 */

/** ISO 8601 날짜·시간 문자열 (예: "2026-10-09T03:00:00Z") */
export type DateTimeString = string

// ── 사용자 · 멤버 ─────────────────────────────────────────────

/** 사용자. 로그인 기능이 생기기 전까지 GET /me 는 고정된 데모 사용자다 (TODO 인증). */
export interface User {
  id: string
  name: string
  email: string
}

export type MemberRole = 'owner' | 'member'

export interface Member {
  user_id: string
  name: string
  email: string
  role: MemberRole
  joined_at: DateTimeString
}

/** POST /workspaces/{id}/members. 개인 워크스페이스에 초대하면 팀 워크스페이스로 바뀐다. 이미 멤버면 409. */
export interface MemberInvite {
  name: string
  /** '@' 가 없으면 422 */
  email: string
}

// ── 워크스페이스 ──────────────────────────────────────────────

/** 개인(혼자 쓰기, 기본값) / 팀(협업). 노션처럼 개인 워크스페이스에 사람을 초대하면 팀이 된다. */
export type WorkspaceKind = 'personal' | 'team'

/** 최상위 단위 (조선소·팀 하나). 프로젝트(블록)·문자/기호 사전·멤버가 워크스페이스에 속한다. */
export interface Workspace {
  id: string
  name: string
  description: string | null
  kind: WorkspaceKind
  member_count: number
  created_at: DateTimeString
}

/** 새 워크스페이스의 문자/기호 사전 시작 방식 */
export type DictionarySource = 'empty' | 'copy'

export interface WorkspaceCreate {
  /** 1~100자 */
  name: string
  description?: string | null
  /** 기본값 'personal'. 만든 사람(현재 사용자)이 소유자가 된다. */
  kind?: WorkspaceKind
  /** 기본값 'empty'. 'copy' 면 copy_from_workspace_id 의 사전을 복제한다. */
  dictionary_source?: DictionarySource
  copy_from_workspace_id?: string | null
}

/** PATCH /workspaces/{id}. 보낸 필드만 바뀐다. 멤버가 2명 이상이면 개인으로 되돌릴 수 없다 (409). */
export interface WorkspaceUpdate {
  name?: string
  description?: string | null
  kind?: WorkspaceKind
}

// ── 프로젝트 (블록, 워크스페이스별) ────────────────────────────

/** 블록 하나 (배 전체가 아닐 수도 있는 조립 단위). 조립 트리와 작업이 프로젝트에 속한다. */
export interface Project {
  id: string
  workspace_id: string
  /** 예: "A1 블록" */
  name: string
  description: string | null
  created_at: DateTimeString
}

export interface ProjectCreate {
  /** 1~100자 */
  name: string
  description?: string | null
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

// ── 조립 트리 (프로젝트별) ────────────────────────────────────

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

/** 셀 한쪽 끝의 관통부 형태 (PAC 과제 타입). 앞/뒤 Collar 는 Collar 판이 붙은 면. */
export type CellFeature = 'slit' | 'slot' | 'collar_front' | 'collar_back' | 'scallop'

/** 셀(블록 안의 칸) 좌·우 끝의 형태. 한쪽에 여러 개가 겹칠 수 있다 (예: 앞 Collar + Scallop). */
export interface Cell {
  left: CellFeature[]
  right: CellFeature[]
}

/** 수기 각장 표기 하나. 예: "F5.5" → code F(3F 용접장), 5.5mm */
export interface LegLength {
  /** 워크스페이스 사전의 code (데모: F 3F 용접장, V 2F 용접장, S 스티프너) */
  code: string
  size_mm: number
  raw_text: string
  /** 해석할 때의 사전 뜻 */
  meaning: string | null
}

export interface Job {
  id: string
  workspace_id: string
  project_id: string
  name: string
  status: JobStatus
  assembly_path: string | null
  related_job_ids: string[]
  created_at: DateTimeString
  approved_at: DateTimeString | null
  approved_by: string | null
  marking: Marking | null
  welding_condition: WeldingCondition | null
  /** 판별한 셀 형태 (해석 전이면 null) */
  cell: Cell | null
  /** 읽은 각장 표기 (읽는 순서) */
  leg_lengths: LegLength[]
  confidence: Confidence | null
  evidence: string[]
  needs_review: string[]
}

/** 작업에 올린 사진 한 장. 파일은 jobImageUrl() */
export interface JobImage {
  image_id: string
  job_id: string
  filename: string
  content_type: string
  /** 원본 픽셀 크기 (1단계 bbox 좌표의 기준) */
  width: number
  height: number
  created_at: DateTimeString
}

// ── 해석 결과 (shared/schemas/analysis.schema.json) ──────────
// 화면에서 쓰는 필드만 옮겨 둔다. 전체 형식과 의미는 shared/schemas 와 shared/README.md 가 기준이다.

/** [x1, y1, x2, y2] 원본 사진 픽셀 좌표 */
export type BBox = [number, number, number, number]

/** [1단계] 읽은 글자 (id: t1, t2, …) */
export interface TextDetection {
  id: string
  text: string
  /** 0~1 */
  prob: number
  bbox: BBox
  /** 유사 문자 후보 (확률이 낮을 때만) */
  candidates?: { text: string; prob: number }[]
}

/** [1단계] 찾은 기호 (id: s1, s2, …). label 은 사전 code, 없으면 "unknown" */
export interface SymbolDetection {
  id: string
  label: string
  prob: number
  bbox: BBox
}

export interface VisionResult {
  image_id: string
  image_size: { width: number; height: number }
  texts: TextDetection[]
  symbols: SymbolDetection[]
}

/** 사진 한 장의 해석 결과. 작업자 확인마다 revision 이 늘어난 새 Analysis 가 쌓인다. */
export interface Analysis {
  analysis_id: string
  job_id: string
  image_id: string
  revision: number
  created_at: DateTimeString
  vision: VisionResult
}

/** POST .../analyze 본문. image_id 를 빼면 가장 최근에 올린 사진 */
export interface AnalyzeRequest {
  image_id?: string
}

export interface JobCreate {
  /** 같은 워크스페이스의 프로젝트 (아니면 422) */
  project_id: string
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
  /** 빈 값·생략이면 워크스페이스 전체 */
  project_id?: string
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

// ── 로봇 연계 JSON (shared/schemas/robot_output.schema.json) ─────────

/** 승인된 작업만 내보낸다. 스키마 파일과 같이 모든 필드 필수 (중첩 객체 포함). */
export interface RobotOutput {
  job_id: string
  workspace_id: string
  project_id: string
  created_at: DateTimeString
  assembly_path: string
  marking: Marking
  welding_condition: WeldingCondition
  cell: Cell | null
  leg_lengths: LegLength[]
  confidence: Confidence
  evidence: string[]
  needs_review: string[]
  approved: boolean
  approved_by: string
}
