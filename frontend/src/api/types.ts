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
  /** 마지막 해석(analyze · review)이 실패한 이유. 상태는 해석 전으로 돌아감. 다음 해석이 성공하면 null */
  analysis_error: string | null
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
  /** 1단계가 보정한 사진(OCR 이 본 사진)이 있는지 — jobPreprocessedUrl() */
  preprocessed: boolean
}

// ── 해석 결과 (shared/schemas/analysis.schema.json) ──────────
// shared/schemas 의 1·2·3단계 형식을 화면에서 쓰는 만큼 옮겨 둔다. 의미와 규칙은 shared/README.md 가 기준이다.
// 확률(prob·score·consistency·factors)은 0~1, 신뢰도(ConfidenceReport 의 네 점수·threshold)는 0~100.

/** [x1, y1, x2, y2] 원본 사진 픽셀 좌표 */
export type BBox = [number, number, number, number]

/** [1단계] a. 전처리에서 실제로 적용한 보정 */
export interface PreprocessStep {
  name: string
  /** 0~1, 클수록 원본을 많이 바꿈 */
  strength: number
}

/** [1단계] b. OCR 로 읽은 글자 (id: t1, t2, …) */
export interface TextDetection {
  id: string
  text: string
  prob: number
  bbox: BBox
  source: string
  /** 글자별 확률 (text 길이와 같음) */
  char_probs?: number[]
  /** 유사 문자 후보 (확률이 낮을 때만, 첫 번째 = text) */
  candidates?: { text: string; prob: number }[]
}

/** [1단계] c. 기호 검출 (id: s1, s2, …). label 은 사전 code, 없으면 "unknown" */
export interface SymbolDetection {
  id: string
  label: string
  prob: number
  bbox: BBox
  source: string
  candidates?: { label: string; prob: number }[]
}

export interface VisionResult {
  image_id: string
  image_size: { width: number; height: number }
  preprocess: { correction_strength: number; steps: PreprocessStep[]; preprocessed_image_uri?: string }
  texts: TextDetection[]
  symbols: SymbolDetection[]
  /** 쓴 모델 이름 (예: {ocr_det, ocr_rec}) */
  models?: Record<string, string>
  elapsed_ms?: number
}

export type MatchKind = 'exact' | 'alias' | 'candidate' | 'fuzzy' | 'vlm' | 'none'

/** [2단계] b. 문자/기호 사전 대조 */
export interface DictionaryMatch {
  ref_ids: string[]
  raw: string
  code: string | null
  meaning: string | null
  match: MatchKind
  score: number
}

/** [2단계] c. 조립 경로 (부재) */
export interface PartMatch {
  node_id: string | null
  assembly_path: string | null
  level: AssemblyLevel | null
  found_in_tree: boolean
  ref_ids: string[]
}

/** [2단계] a. 용접 기준 DB 로 판별한 조건 */
export interface ContextWeldingCondition extends WeldingCondition {
  thickness_mm?: number | null
  /** 판 두께 없이 각장으로 기준 행을 고른 경우의 각장 */
  leg_length_mm?: number | null
  standard_matched: boolean
  source: 'standard_db' | 'vlm' | 'manual'
  ref_ids?: string[]
}

export type ConflictType =
  | 'dictionary_unmatched'
  | 'part_not_in_tree'
  | 'standard_conflict'
  | 'ocr_vlm_mismatch'
  | 'ambiguous_reading'

export interface Conflict {
  type: ConflictType
  severity: 'info' | 'warning' | 'error'
  message: string
  ref_ids: string[]
}

/** [2단계] d. VLM 맥락 해석 (VLM 을 끄면 null) */
export interface VlmResult {
  provider: string
  model: string
  interpretation: string
  /** 사진을 보고 해석했는지 (없으면 모름) */
  image_attached?: boolean
  reading: {
    /** used: 1단계와 다르게 읽었고 2단계가 이 VLM 읽기를 해석에 씀 */
    texts: { text: string; ref_id: string; bbox?: BBox; used?: boolean }[]
    symbols: { label: string; ref_id: string; bbox?: BBox; used?: boolean }[]
  }
  token_prob: number | null
  consistency: number | null
  runs: number
}

/** [2단계] 수기 각장 (PAC 과제) */
export interface ContextLegLength extends LegLength {
  ref_ids: string[]
}

/** [2단계] 셀 좌·우 끝 형태 (PAC 과제) */
export interface ContextCell extends Cell {
  ref_ids: string[]
}

export interface ContextResult {
  user_context?: string | null
  related_job_ids?: string[]
  dictionary_matches: DictionaryMatch[]
  part: PartMatch
  welding_condition: ContextWeldingCondition | null
  leg_lengths: ContextLegLength[]
  cell: ContextCell | null
  conflicts: Conflict[]
  vlm: VlmResult | null
  /** VLM 을 켰는데 추론이 모두 실패한 이유 (이때 vlm 은 null) */
  vlm_error?: string | null
}

export type ConfidenceLayer = 'visual' | 'db_consistency' | 'vlm_reasoning'

/** [3단계] 신뢰도 산출 */
export interface ConfidenceReport {
  visual: number
  db_consistency: number
  vlm_reasoning: number
  overall: number
  threshold: number
  passed: boolean
  factors: {
    visual: { recognition_prob: number | null; correction_strength: number | null; ocr_vlm_agreement: number | null }
    db_consistency: { dictionary_match_rate: number | null; part_found: boolean | null; standard_conflicts: number }
    vlm_reasoning: { token_prob: number | null; consistency: number | null }
  }
  evidence: { layer: ConfidenceLayer; message: string; ref_ids?: string[] }[]
  needs_review: { target: string; reason: string; message: string; candidates?: string[] }[]
}

/** 작업자가 고친 항목 (target: t*·s*·v*·part·interpretation·welding_condition) */
export interface Correction {
  target: string
  value: unknown
  meaning?: string
  previous?: unknown
}

/** 사진 한 장의 해석 결과. 작업자 확인마다 revision 이 늘어난 새 Analysis 가 쌓인다. */
export interface Analysis {
  schema_version: string
  analysis_id: string
  workspace_id: string
  project_id: string
  job_id: string
  image_id: string
  revision: number
  created_at: DateTimeString
  vision: VisionResult
  context: ContextResult
  confidence: ConfidenceReport | null
  corrections?: Correction[]
}

/** GET /pipeline/status — 단계별 모델·API 연결 상태 (API 키 값은 오지 않는다) */
export interface PipelineStatus {
  ocr_available: boolean
  ocr_models: Record<string, string>
  symbol_detector_available: boolean
  vlm_provider: string | null
  vlm_model: string | null
  vlm_runs: number
  vlm_sdk_installed: boolean
  vlm_api_key_set: boolean
  /** 서버를 켠 뒤 가장 최근 VLM 호출 실패 이유 (그다음 성공하면 null) */
  vlm_last_error: string | null
  vlm_last_error_at: DateTimeString | null
  confidence_threshold: number
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
  /** 확인 필요(needs_review) 작업을 승인할 때 true — 작업자가 확인 항목을 직접 봤다는 표시 (없으면 409) */
  acknowledge_review?: boolean
}

// ── 표준 용접 기준 (전체 공통, 읽기 전용) ─────────────────────

/** 판 두께 또는 각장으로 고르는 기준 행. 각장별 값만 있는 행(3F)은 판 두께가 null, 맞대기는 각장이 null */
export interface WeldingStandard {
  joint_type: string
  thickness_min_mm: number | null
  thickness_max_mm: number | null
  leg_min_mm: number | null
  leg_max_mm: number | null
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
