"""API 스키마 (Pydantic v2) — 프론트엔드와 공유하는 계약. 필드명은 snake_case, id 는 문자열."""
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Self

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


# 시각은 시간대 필수, UTC 로 정규화해 "...Z" 로 응답한다.
# (stdlib UTC 로 바꿔 두면 pydantic-core TzInfo 가 남지 않는다 — Python 3.12 -X dev 종료 시 GC segfault 회피)
UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]  # 워크스페이스·프로젝트 이름
Score = Annotated[float, Field(ge=0, le=100)]

WorkspaceKind = Literal["personal", "team"]  # 개인 / 팀(협업)
MemberRole = Literal["owner", "member"]
SymbolKind = Literal["text", "symbol"]
AssemblyLevel = Literal["BLOCK", "LARGE", "MID", "SUB", "PART"]
JobStatus = Literal["draft", "analyzing", "needs_review", "awaiting_approval", "approved"]
ReviewAction = Literal["reinterpret", "manual"]


class ApiModel(BaseModel):
    """모든 API 모델의 기반. 응답 스키마(OpenAPI)에서는 기본값이 있는 필드도 필수로 표시한다 — 응답 JSON 에는 항상 들어 있다."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class ErrorDetail(ApiModel):
    """오류 응답 본문 (404·409·501 등). 422 검증 오류는 FastAPI 기본 형식(detail 배열)."""

    detail: str


def _require_at(value: str) -> str:
    if "@" not in value:
        raise ValueError("이메일 형식이 아닙니다 ('@' 가 필요합니다)")
    return value


# 이메일은 '@' 포함 여부만 확인한다 (email-validator 의존성 없이)
Email = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1), AfterValidator(_require_at)]


# ── 사용자 ────────────────────────────────────────────────────

class User(ApiModel):
    id: str
    name: str
    email: str


# ── 워크스페이스 ──────────────────────────────────────────────

class Workspace(ApiModel):
    """kind: 개인(personal) / 팀(team). 개인 워크스페이스에 멤버를 초대하면 팀으로 바뀐다."""

    id: str
    name: str
    description: str | None = None
    kind: WorkspaceKind
    member_count: int  # 멤버 수 (소유자 포함) — 저장소가 멤버 목록에서 계산
    created_at: UtcDatetime


class WorkspaceCreate(ApiModel):
    """현재 사용자가 새 워크스페이스의 소유자(owner) 멤버가 된다."""

    name: Name
    description: str | None = None
    kind: WorkspaceKind = "personal"
    dictionary_source: Literal["empty", "copy"] = "empty"
    copy_from_workspace_id: str | None = None  # dictionary_source 가 "copy" 일 때만 사용

    @model_validator(mode="after")
    def _require_copy_source(self) -> Self:
        if self.dictionary_source == "copy" and not self.copy_from_workspace_id:
            raise ValueError("dictionary_source 가 'copy' 이면 copy_from_workspace_id 가 필요합니다")
        return self


class WorkspaceUpdate(ApiModel):
    """부분 수정 — 보낸 필드만 바뀐다. null 로 비울 수 있는 필드는 description 뿐.

    kind 를 team → personal 로 바꾸는 것은 멤버가 1명(소유자)일 때만 (아니면 409).
    """

    name: Name = None
    description: str | None = None
    kind: WorkspaceKind = None


class Member(ApiModel):
    user_id: str
    name: str
    email: str
    role: MemberRole
    joined_at: UtcDatetime


class MemberInvite(ApiModel):
    """이메일이 같은 사용자(대소문자 무시)가 있으면 그 사용자를, 없으면 새 사용자를 만들어 초대한다."""

    name: NonEmptyStr
    email: Email


# ── 프로젝트 (블록) ───────────────────────────────────────────

class Project(ApiModel):
    """워크스페이스 안의 블록 하나 — 조립 트리와 작업이 프로젝트에 속한다."""

    id: str
    workspace_id: str
    name: str
    description: str | None = None
    created_at: UtcDatetime


class ProjectCreate(ApiModel):
    name: Name
    description: str | None = None


# ── 문자/기호 사전 ────────────────────────────────────────────

class SymbolEntry(ApiModel):
    id: str
    code: str
    kind: SymbolKind
    meaning: str
    aliases: list[str] = []
    welding_joint_type: str | None = None  # 용접 기준의 joint_type (예: FILLET, BUTT_V)


class SymbolEntryCreate(ApiModel):
    code: NonEmptyStr
    kind: SymbolKind
    meaning: NonEmptyStr
    aliases: list[str] = []
    welding_joint_type: str | None = None


class SymbolEntryUpdate(ApiModel):
    """부분 수정 — 보낸 필드만 바뀐다. null 로 비울 수 있는 필드는 welding_joint_type 뿐.

    나머지 필드의 기본값 None 은 '보내지 않음' 표시일 뿐이다 (기본값은 검증하지 않으므로 생략 가능,
    null 을 보내면 타입 검증에서 422).
    """

    code: NonEmptyStr = None
    kind: SymbolKind = None
    meaning: NonEmptyStr = None
    aliases: list[str] = None
    welding_joint_type: str | None = None


# ── 조립 트리 (프로젝트별) ────────────────────────────────────

class AssemblyNode(ApiModel):
    node_id: str
    parent_id: str | None = None
    level: AssemblyLevel
    path: str


# ── 작업 ──────────────────────────────────────────────────────

class Marking(ApiModel):
    raw_text: str
    symbols: list[str] = []
    interpretation: str


class WeldingCondition(ApiModel):
    joint_type: str
    process: str
    position: str
    current_a: str     # 범위 문자열, 예: "220-260"
    voltage_v: str
    speed_cm_min: str


class Confidence(ApiModel):
    visual: Score
    db_consistency: Score
    vlm_reasoning: Score
    overall: Score


class Job(ApiModel):
    id: str
    workspace_id: str
    project_id: str
    name: str
    status: JobStatus
    assembly_path: str | None = None
    related_job_ids: list[str] = []
    created_at: UtcDatetime
    approved_at: UtcDatetime | None = None
    approved_by: str | None = None
    marking: Marking | None = None
    welding_condition: WeldingCondition | None = None
    confidence: Confidence | None = None
    evidence: list[str] = []
    needs_review: list[str] = []


class JobCreate(ApiModel):
    name: NonEmptyStr
    project_id: NonEmptyStr  # 같은 워크스페이스의 프로젝트만 (아니면 422)
    assembly_path: str | None = None
    related_job_ids: list[str] = []


class ReviewRequest(ApiModel):
    action: ReviewAction
    context: str | None = None           # reinterpret: 작업자가 추가한 맥락
    values: dict[str, Any] | None = None  # manual: 작업자가 직접 입력한 해석 값


class ApproveRequest(ApiModel):
    approved_by: NonEmptyStr


# ── 표준 용접 기준 (공통, 읽기 전용) ──────────────────────────

class WeldingStandard(ApiModel):
    joint_type: str
    thickness_min_mm: float
    thickness_max_mm: float
    process: str
    position: str
    current_a: str
    voltage_v: str
    speed_cm_min: str


# ── 로봇 연계 JSON (schemas/robot_output.schema.json) ─────────

class RobotOutput(ApiModel):
    """스키마 파일과 같은 모양 — 모든 필드 필수 (중첩 객체의 필드 포함)"""

    job_id: str
    workspace_id: str
    project_id: str
    created_at: UtcDatetime
    assembly_path: str
    marking: Marking
    welding_condition: WeldingCondition
    confidence: Confidence
    evidence: list[str]
    needs_review: list[str]
    approved: bool
    approved_by: str
