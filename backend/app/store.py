"""저장소 (워크스페이스 단위) — 메모리에 두고, DATABASE_URL 의 DB 에도 남긴다
(postgresql://… → PostgreSQL app/db/postgres.py · sqlite:///… → SQLite 파일 app/db/sqlite.py, app/db/connect.py 가 고름)

DB 가 비어 있으면 data/seed 의 초기 상태(팀 워크스페이스 "demo", 개인 워크스페이스 "personal")로 시작해 그대로 저장하고,
그다음부터는 DB 에서 읽는다 — 서버를 다시 켜도 작업 · 사진 · 해석 결과가 남는다. 시드 상태로 되돌리려면 DB 를 비운다.
테스트(reset_store)는 DB 없이 메모리만 쓴다.
TODO(인증): 로그인 없음 — 요청 헤더 X-User-Id 가 데모 사용자를 고르고(없으면 시드의 current_user_id),
  워크스페이스 목록만 그 사용자가 멤버인 것으로 거른다. 그 밖의 권한 검사는 없어 누구나 모든 워크스페이스에 접근할 수 있다.

- 워크스페이스별 데이터(멤버, 문자/기호 사전, 프로젝트, 작업)는 workspace_id 를 키로 하는 dict 에 둔다.
- 조립 트리는 프로젝트(블록)별 — assembly_trees[workspace_id][project_id]. 작업은 project_id 필드로 프로젝트에 속한다.
- 사용자와 표준 용접 기준은 모든 워크스페이스가 공유하는 공통 데이터다 (용접 기준은 읽기 전용, 늘 CSV 에서 읽음).
- 확인 후 변경하는 작업(승인, 사전 항목 수정·삭제, 워크스페이스 수정, 멤버 초대)은 잠금 안에서 최신 상태를
  다시 읽어 처리한다 — 동시 요청이 같은 스냅샷을 보고 둘 다 성공하지 않도록.
- 바꾸는 메서드는 모두 바뀐 항목을 _put 으로 파일에 남긴다 (새 메서드를 만들면 같이 부를 것).
"""
import json
import os
import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from app.db.assembly_tree import LEVELS, load_tree
from app.db.connect import DocumentDB, open_database
from app.db.sqlite import Database
from app.db.symbol_dictionary import load_symbols
from app.db.welding_standards import load_standards
from app.schemas import (
    AnalysisStage,
    AssemblyNode,
    AssemblyNodeCreate,
    Job,
    JobCreate,
    JobImage,
    JobStatus,
    Member,
    Project,
    ProjectCreate,
    SymbolEntry,
    SymbolEntryCreate,
    User,
    WeldingStandard,
    Workspace,
    WorkspaceKind,
)

SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seed"

# 승인할 수 있는 작업 상태 — 확인 필요(needs_review)는 작업자가 확인 항목을 직접 봤다고 표시해야(acknowledge_review) 승인
APPROVABLE: frozenset[JobStatus] = frozenset({"awaiting_approval", "needs_review"})
# 로봇 JSON 에 꼭 필요한 해석 결과 (app/export/robot_json.py) — 비어 있으면 승인하지 않음
REQUIRED_FOR_APPROVAL = ("assembly_path", "marking", "welding_condition")


class JobStatusConflict(Exception):
    """현재 상태에서는 할 수 없는 작업 상태 변경 (API 에서는 409)"""

    def __init__(self, status: JobStatus) -> None:
        super().__init__(status)
        self.status = status


class ReviewNotAcknowledged(Exception):
    """확인 필요 작업을 확인 항목을 봤다는 표시(acknowledge_review) 없이 승인하려 함 (API 에서는 409)"""

    def __init__(self, needs_review: list[str]) -> None:
        super().__init__(needs_review)
        self.needs_review = needs_review


class MissingForApproval(Exception):
    """로봇 JSON 에 필요한 해석 결과가 비어 있어 승인할 수 없음 (API 에서는 409)"""

    def __init__(self, missing: list[str]) -> None:
        super().__init__(missing)
        self.missing = missing


class WorkspaceKindConflict(Exception):
    """멤버가 여럿인 팀 워크스페이스를 개인으로 바꾸려 함 (API 에서는 409)"""

    def __init__(self, member_count: int) -> None:
        super().__init__(member_count)
        self.member_count = member_count


class MemberAlreadyExists(Exception):
    """이미 워크스페이스 멤버인 이메일을 다시 초대함 (API 에서는 409)"""

    def __init__(self, email: str) -> None:
        super().__init__(email)
        self.email = email


class AssemblyNodeInvalid(Exception):
    """조립 경로 사전에 넣을 수 없는 노드 — 상위 노드 없음, 단계가 상위보다 위 (API 에서는 422)"""


class AssemblyNodeConflict(Exception):
    """이미 있는 조립 경로, 아래 노드가 있는 노드를 지움 (API 에서는 409)"""


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(UTC)


class Store:
    def __init__(self, db: DocumentDB | None = None) -> None:
        self._db = db
        self.users: dict[str, User] = {}
        self.current_user_id: str | None = None
        self.workspaces: dict[str, Workspace] = {}
        # 멤버의 name·email 은 가입 시점 사용자 정보 복사본 (사용자 수정 API 없음 — DB 로 바꾸면 users 조인)
        self.members: dict[str, dict[str, Member]] = {}  # workspace_id → user_id → Member
        self.symbols: dict[str, dict[str, SymbolEntry]] = {}
        self.projects: dict[str, dict[str, Project]] = {}
        self.assembly_trees: dict[str, dict[str, list[AssemblyNode]]] = {}  # workspace_id → project_id → 노드
        self.jobs: dict[str, dict[str, Job]] = {}
        # 작업에 올린 사진과 해석 결과 (Analysis, shared/schemas/analysis.schema.json) — job_id 가 키
        # TODO: 사진 파일은 지금 메모리에만 둔다. 실제 DB 로 바꿀 때 data/uploads/ 나 오브젝트 스토리지로 옮긴다.
        self.images: dict[str, list[JobImage]] = {}
        self.image_data: dict[str, bytes] = {}  # image_id → 파일 바이트
        self.preprocessed: dict[str, bytes] = {}  # image_id → 1단계가 보정한 사진 (PNG, 보정한 게 없으면 없음)
        self.analyses: dict[str, list[dict]] = {}
        self.welding_standards: list[WeldingStandard] = []
        self._lock = threading.RLock()

    # ── DB 에 남기기 (app/db/connect.py) ──
    def _put(self, collection: str, key: str, value) -> None:
        if self._db is not None:
            self._db.put(collection, key, value.model_dump(mode="json") if isinstance(value, BaseModel) else value)

    def _delete(self, collection: str, key: str) -> None:
        if self._db is not None:
            self._db.delete(collection, key)

    def attach(self, db: DocumentDB) -> None:
        """지금 상태를 통째로 db 에 쓰고, 이후 바뀌는 것을 계속 남긴다 (시드로 처음 시작할 때)"""
        with self._lock:
            self._db = db
            self._put("meta", "current_user_id", self.current_user_id)
            for user in self.users.values():
                self._put("users", user.id, user)
            for ws_id, workspace in self.workspaces.items():
                self._put("workspaces", ws_id, workspace)
                for member in self.members[ws_id].values():
                    self._put("members", f"{ws_id}/{member.user_id}", member)
                for entry in self.symbols[ws_id].values():
                    self._put("symbols", f"{ws_id}/{entry.id}", entry)
                for project in self.projects[ws_id].values():
                    self._put_project(project)
                for job in self.jobs[ws_id].values():
                    self._put("jobs", f"{ws_id}/{job.id}", job)
            for job_id, images in self.images.items():
                for image in images:
                    self._put("images", f"{job_id}/{image.image_id}", image)
                    db.put_blob("image", image.image_id, self.image_data[image.image_id])
            for image_id, data in self.preprocessed.items():
                db.put_blob("preprocessed", image_id, data)
            for job_id, analyses in self.analyses.items():
                for i, analysis in enumerate(analyses):
                    self._put("analyses", f"{job_id}/{i:06d}", analysis)

    def _put_project(self, project: Project) -> None:
        key = f"{project.workspace_id}/{project.id}"
        self._put("projects", key, project)
        self._put("trees", key, [n.model_dump(mode="json") for n in self.assembly_trees[project.workspace_id][project.id]])

    # ── 사용자 ──
    def list_users(self) -> list[User]:
        """시드 순서 (초대로 만든 사용자는 그 뒤에)"""
        return list(self.users.values())

    def get_user(self, user_id: str) -> User | None:
        return self.users.get(user_id)

    def default_user(self) -> User:
        """TODO(인증): X-User-Id 헤더가 없을 때의 현재 사용자 — 시드의 current_user_id (데모 사용자)"""
        return self.users[self.current_user_id]

    def find_user_by_email(self, email: str) -> User | None:
        needle = email.strip().casefold()
        return next((u for u in self.users.values() if u.email.casefold() == needle), None)

    # ── 워크스페이스 ──
    def list_workspaces(self, member_id: str | None = None) -> list[Workspace]:
        """추가된 순서 — 시드(폴더 이름순) 다음에 새로 만든 워크스페이스가 생성 순으로 온다.

        member_id 가 있으면 그 사용자가 멤버인 워크스페이스만.
        """
        return [w for w in self.workspaces.values() if member_id is None or member_id in self.members[w.id]]

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        return self.workspaces.get(workspace_id)

    def add_workspace(
        self,
        workspace: Workspace,
        members: Iterable[Member],
        symbols: Iterable[SymbolEntry] = (),
    ) -> Workspace:
        """member_count 는 members 로 다시 계산해 저장한다."""
        members = list(members)
        workspace = workspace.model_copy(update={"member_count": len(members)})
        with self._lock:
            self.workspaces[workspace.id] = workspace
            self.members[workspace.id] = {m.user_id: m for m in members}
            self.symbols[workspace.id] = {s.id: s for s in symbols}
            self.projects[workspace.id] = {}
            self.assembly_trees[workspace.id] = {}
            self.jobs[workspace.id] = {}
            self._put("workspaces", workspace.id, workspace)
            for m in members:
                self._put("members", f"{workspace.id}/{m.user_id}", m)
            for entry in self.symbols[workspace.id].values():
                self._put("symbols", f"{workspace.id}/{entry.id}", entry)
        return workspace

    def create_workspace(
        self,
        name: str,
        owner: User,
        description: str | None = None,
        kind: WorkspaceKind = "personal",
        copy_symbols_from: str | None = None,
    ) -> Workspace:
        """새 워크스페이스 — owner 가 유일한 소유자 멤버. copy_symbols_from 이 있으면 그 사전을 새 id 로 복제한다."""
        symbols = [
            s.model_copy(update={"id": new_id("sym")}, deep=True)
            for s in (self.list_symbols(copy_symbols_from) if copy_symbols_from else [])
        ]
        now = utcnow()
        workspace = Workspace(
            id=new_id("ws"), name=name, description=description, kind=kind, member_count=1, created_at=now
        )
        owner_member = Member(user_id=owner.id, name=owner.name, email=owner.email, role="owner", joined_at=now)
        return self.add_workspace(workspace, members=[owner_member], symbols=symbols)

    def update_workspace(self, workspace_id: str, changes: dict) -> Workspace | None:
        """보낸 필드만 바꾼다. 없는 워크스페이스면 None.

        team → personal 은 멤버가 1명일 때만 (아니면 WorkspaceKindConflict) — 초대와 동시에 와도 잠금 안에서 판단한다.
        """
        with self._lock:
            workspace = self.workspaces.get(workspace_id)
            if workspace is None:
                return None
            if changes.get("kind") == "personal" and workspace.member_count > 1:
                raise WorkspaceKindConflict(workspace.member_count)
            workspace = Workspace.model_validate({**workspace.model_dump(), **changes})
            self.workspaces[workspace_id] = workspace
            self._put("workspaces", workspace_id, workspace)
            return workspace

    # ── 멤버 ──
    def list_members(self, workspace_id: str) -> list[Member]:
        """소유자 먼저, 그다음 가입 순"""
        return sorted(self.members[workspace_id].values(), key=lambda m: (m.role != "owner", m.joined_at))

    def invite_member(self, workspace_id: str, name: str, email: str) -> Member:
        """이메일로 멤버 초대 (role "member"). 같은 이메일(대소문자 무시)의 사용자가 없으면 만든다.

        이미 멤버면 MemberAlreadyExists. 개인 워크스페이스는 같은 잠금 안에서 팀으로 바뀐다.
        """
        with self._lock:
            members = self.members[workspace_id]
            user = self.find_user_by_email(email)
            if user is not None and user.id in members:
                raise MemberAlreadyExists(email)
            if user is None:
                user = User(id=new_id("user"), name=name, email=email)
                self.users[user.id] = user
                self._put("users", user.id, user)
            member = Member(user_id=user.id, name=user.name, email=user.email, role="member", joined_at=utcnow())
            members[user.id] = member
            self.workspaces[workspace_id] = self.workspaces[workspace_id].model_copy(
                update={"kind": "team", "member_count": len(members)}
            )
            self._put("members", f"{workspace_id}/{user.id}", member)
            self._put("workspaces", workspace_id, self.workspaces[workspace_id])
            return member

    # ── 문자/기호 사전 ──
    def list_symbols(self, workspace_id: str) -> list[SymbolEntry]:
        return list(self.symbols[workspace_id].values())

    def get_symbol(self, workspace_id: str, symbol_id: str) -> SymbolEntry | None:
        return self.symbols[workspace_id].get(symbol_id)

    def create_symbol(self, workspace_id: str, data: SymbolEntryCreate) -> SymbolEntry:
        return self.save_symbol(workspace_id, SymbolEntry(id=new_id("sym"), **data.model_dump()))

    def save_symbol(self, workspace_id: str, entry: SymbolEntry) -> SymbolEntry:
        with self._lock:
            self.symbols[workspace_id][entry.id] = entry
            self._put("symbols", f"{workspace_id}/{entry.id}", entry)
        return entry

    def update_symbol(self, workspace_id: str, symbol_id: str, changes: dict) -> SymbolEntry | None:
        """보낸 필드만 바꾼다. 없는 항목이면 None (삭제와 동시에 와도 되살리지 않는다)."""
        with self._lock:
            entry = self.symbols[workspace_id].get(symbol_id)
            if entry is None:
                return None
            return self.save_symbol(workspace_id, SymbolEntry.model_validate({**entry.model_dump(), **changes}))

    def delete_symbol(self, workspace_id: str, symbol_id: str) -> bool:
        with self._lock:
            removed = self.symbols[workspace_id].pop(symbol_id, None) is not None
            if removed:
                self._delete("symbols", f"{workspace_id}/{symbol_id}")
            return removed

    # ── 프로젝트 (블록) ──
    def list_projects(self, workspace_id: str) -> list[Project]:
        """생성 순 (오래된 것부터)"""
        return sorted(self.projects[workspace_id].values(), key=lambda p: p.created_at)

    def get_project(self, workspace_id: str, project_id: str) -> Project | None:
        return self.projects[workspace_id].get(project_id)

    def add_project(self, project: Project, assembly_tree: Iterable[AssemblyNode] = ()) -> Project:
        with self._lock:
            self.projects[project.workspace_id][project.id] = project
            self.assembly_trees[project.workspace_id][project.id] = list(assembly_tree)
            self._put_project(project)
        return project

    def create_project(self, workspace_id: str, data: ProjectCreate) -> Project:
        """새 프로젝트 — 조립 트리는 비어 있다."""
        return self.add_project(
            Project(id=new_id("prj"), workspace_id=workspace_id, created_at=utcnow(), **data.model_dump())
        )

    def default_project(self, workspace_id: str) -> Project:
        """작업을 담는 기본 프로젝트 — 화면에는 블록 층이 없어서(워크스페이스 → 작업) 작업을 만들 때 프로젝트를 고르지 않는다.
        가장 오래된 프로젝트, 없으면 하나 만든다"""
        with self._lock:
            existing = self.list_projects(workspace_id)
            return existing[0] if existing else self.create_project(workspace_id, ProjectCreate(name="작업"))

    # ── 조립 트리 ──
    def get_assembly_tree(self, workspace_id: str, project_id: str) -> list[AssemblyNode]:
        return list(self.assembly_trees[workspace_id][project_id])

    def get_workspace_assembly_tree(self, workspace_id: str) -> list[AssemblyNode]:
        """워크스페이스의 조립 트리 하나 (조립 경로 사전) — 프로젝트별로 나눠 저장된 트리를 합침, 같은 경로는 한 번만"""
        nodes: dict[str, AssemblyNode] = {}
        for project in self.list_projects(workspace_id):
            for node in self.assembly_trees[workspace_id][project.id]:
                nodes.setdefault(node.path, node)
        return list(nodes.values())

    def add_assembly_node(self, workspace_id: str, data: AssemblyNodeCreate) -> AssemblyNode:
        """조립 경로 사전에 노드 추가 — 상위 노드가 있는 프로젝트(블록)의 트리에, 최상위면 기본 프로젝트에 넣는다"""
        with self._lock:
            tree = {n.path: n for n in self.get_workspace_assembly_tree(workspace_id)}
            parent = None
            if data.parent_path is not None:
                parent = tree.get(data.parent_path)
                if parent is None:
                    raise AssemblyNodeInvalid(f"상위 노드가 조립 경로 사전에 없습니다: {data.parent_path}")
            depth = LEVELS.index(parent.level) + 1 if parent else 0
            if depth == len(LEVELS):
                raise AssemblyNodeInvalid("부재(PART) 아래에는 노드를 넣을 수 없습니다")
            level = data.level or LEVELS[depth]
            if LEVELS.index(level) < depth:
                raise AssemblyNodeInvalid(f"{level} 은 상위 노드({parent.level})보다 아래 단계여야 합니다")
            path = f"{parent.path}/{data.node_id}" if parent else data.node_id
            if path in tree:
                raise AssemblyNodeConflict(f"이미 있는 조립 경로입니다: {path}")
            project = next(
                (p for p in self.list_projects(workspace_id)
                 if parent and any(n.path == parent.path for n in self.assembly_trees[workspace_id][p.id])),
                None,
            ) or self.default_project(workspace_id)
            node = AssemblyNode(node_id=data.node_id, parent_id=parent.node_id if parent else None, level=level, path=path)
            self.assembly_trees[workspace_id][project.id].append(node)
            self._put_project(project)
            return node

    def delete_assembly_node(self, workspace_id: str, path: str) -> bool:
        """조립 경로 사전에서 노드 하나 지우기 (같은 경로가 여러 블록에 있으면 모두). 아래 노드가 있으면 AssemblyNodeConflict"""
        with self._lock:
            tree = self.get_workspace_assembly_tree(workspace_id)
            if not any(n.path == path for n in tree):
                return False
            if any(n.path.startswith(f"{path}/") for n in tree):
                raise AssemblyNodeConflict(f"아래 노드가 있어 지울 수 없습니다. 아래 노드부터 지워 주세요: {path}")
            for project in self.list_projects(workspace_id):
                nodes = self.assembly_trees[workspace_id][project.id]
                if any(n.path == path for n in nodes):
                    self.assembly_trees[workspace_id][project.id] = [n for n in nodes if n.path != path]
                    self._put_project(project)
            return True

    # ── 작업 ──
    def list_jobs(
        self,
        workspace_id: str,
        q: str | None = None,
        status: JobStatus | None = None,
        project_id: str | None = None,
    ) -> list[Job]:
        """작업 DB 검색. q 는 이름·조립 경로·표기 원문/해석에서 대소문자 무시 부분 일치. 최신순."""
        jobs = list(self.jobs[workspace_id].values())
        if project_id:
            jobs = [j for j in jobs if j.project_id == project_id]
        if status:
            jobs = [j for j in jobs if j.status == status]
        if q and (needle := q.strip().casefold()):
            jobs = [j for j in jobs if any(needle in text.casefold() for text in _searchable(j))]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def get_job(self, workspace_id: str, job_id: str) -> Job | None:
        return self.jobs[workspace_id].get(job_id)

    def create_job(self, workspace_id: str, data: JobCreate) -> Job:
        job = Job(id=new_id("job"), workspace_id=workspace_id, status="draft", created_at=utcnow(), **data.model_dump())
        return self.save_job(job)

    def save_job(self, job: Job) -> Job:
        with self._lock:
            self.jobs[job.workspace_id][job.id] = job
            self._put("jobs", f"{job.workspace_id}/{job.id}", job)
        return job

    def start_analysis(self, workspace_id: str, job_id: str, stage: AnalysisStage = "vision") -> Job | None:
        """해석을 시작하며 상태를 analyzing 으로, 첫 단계는 stage (이미 해석 중이면 JobStatusConflict). 없는 작업이면 None.
        끝나면 호출한 쪽이 결과를 save_job 하거나 실패를 finish_failed_analysis 로 남긴다"""
        with self._lock:
            job = self.get_job(workspace_id, job_id)
            if job is None:
                return None
            if job.status == "analyzing":
                raise JobStatusConflict(job.status)
            return self.save_job(job.model_copy(update={
                "status": "analyzing", "analysis_error": None, "analysis_stage": stage, "analysis_stage_at": utcnow(),
            }))

    def set_analysis_stage(self, workspace_id: str, job_id: str, stage: AnalysisStage) -> None:
        """해석 중인 작업의 지금 단계 (해석이 이미 끝났으면 무시)"""
        with self._lock:
            job = self.get_job(workspace_id, job_id)
            if job is not None and job.status == "analyzing" and job.analysis_stage != stage:
                self.save_job(job.model_copy(update={"analysis_stage": stage, "analysis_stage_at": utcnow()}))

    def finish_failed_analysis(self, job: Job, error: str) -> Job:
        """해석 실패 → 해석 전 상태(job)로 돌리고 이유를 남김"""
        return self.save_job(job.model_copy(update={"analysis_error": error, "analysis_stage": None, "analysis_stage_at": None}))

    def approve_job(self, workspace_id: str, job_id: str, approved_by: str, acknowledge_review: bool = False) -> Job | None:
        """승인 대기 상태, 또는 작업자가 확인 항목을 봤다고 표시한(acknowledge_review) 확인 필요 상태만 승인한다.
        상태가 안 맞으면 JobStatusConflict, 확인 표시가 없으면 ReviewNotAcknowledged, 로봇 JSON 에 필요한 값이 비어 있으면
        MissingForApproval. 없는 작업이면 None.

        상태 확인과 저장을 한 잠금 안에서 해 동시에 여러 번 승인해도 하나만 성공한다.
        """
        with self._lock:
            job = self.get_job(workspace_id, job_id)
            if job is None:
                return None
            if job.status not in APPROVABLE:
                raise JobStatusConflict(job.status)
            if missing := [name for name in REQUIRED_FOR_APPROVAL if getattr(job, name) is None]:
                raise MissingForApproval(missing)
            if job.status == "needs_review" and not acknowledge_review:
                raise ReviewNotAcknowledged(job.needs_review)
            return self.save_job(
                job.model_copy(update={"status": "approved", "approved_at": utcnow(), "approved_by": approved_by})
            )


    # ── 사진 · 해석 결과 (Analysis) ──
    def add_image(self, job: Job, filename: str, content_type: str, data: bytes, width: int, height: int) -> JobImage:
        image = JobImage(image_id=new_id("img"), job_id=job.id, filename=filename, content_type=content_type,
                         width=width, height=height, created_at=utcnow())
        with self._lock:
            self.image_data[image.image_id] = data
            self.images.setdefault(job.id, []).append(image)
            self._put("images", f"{job.id}/{image.image_id}", image)
            if self._db is not None:
                self._db.put_blob("image", image.image_id, data)
        return image

    def set_preprocessed(self, job_id: str, image_id: str, data: bytes) -> None:
        """1단계가 보정한 사진 (PNG). JobImage.preprocessed 를 true 로"""
        with self._lock:
            images = self.images.get(job_id, [])
            index = next((i for i, image in enumerate(images) if image.image_id == image_id), None)
            if index is None:
                return
            self.preprocessed[image_id] = data
            images[index] = images[index].model_copy(update={"preprocessed": True})
            self._put("images", f"{job_id}/{image_id}", images[index])
            if self._db is not None:
                self._db.put_blob("preprocessed", image_id, data)

    def get_preprocessed(self, image_id: str) -> bytes | None:
        return self.preprocessed.get(image_id)

    def list_images(self, job_id: str) -> list[JobImage]:
        """올린 순서 (가장 최근이 마지막)"""
        return list(self.images.get(job_id, []))

    def get_image(self, job_id: str, image_id: str) -> tuple[JobImage, bytes] | None:
        image = next((i for i in self.images.get(job_id, []) if i.image_id == image_id), None)
        return (image, self.image_data[image_id]) if image else None

    def add_analysis(self, job_id: str, analysis: dict) -> dict:
        with self._lock:
            analyses = self.analyses.setdefault(job_id, [])
            analyses.append(analysis)
            self._put("analyses", f"{job_id}/{len(analyses) - 1:06d}", analysis)
        return analysis

    def list_analyses(self, job_id: str) -> list[dict]:
        """만든 순서 (사진마다 revision 1, 작업자 확인마다 revision + 1). Job 에는 가장 최근 것이 반영돼 있다"""
        return list(self.analyses.get(job_id, []))


def _searchable(job: Job) -> list[str]:
    texts = [job.name, job.assembly_path or ""]
    if job.marking:
        texts += [job.marking.raw_text, job.marking.interpretation]
    return texts


def _read_json(path: Path) -> dict | list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _subdirs(path: Path) -> list[Path]:
    """하위 폴더 (이름순). 폴더가 없으면 빈 목록."""
    return sorted(p for p in path.iterdir() if p.is_dir()) if path.is_dir() else []


def load_seed(store: Store, seed_dir: Path = SEED_DIR) -> Store:
    """data/seed 를 읽어 공통 데이터(사용자, 용접 기준)와 시드 워크스페이스(demo, park, personal)를 채운다.

    사용자: users.json — {"current_user_id": ..., "users": [User, ...]}
    워크스페이스: workspaces/<workspace_id>/{workspace.json, members.json, symbol_dictionary.json(없으면 빈 사전)}
    프로젝트(블록): workspaces/<workspace_id>/projects/<project_id>/{project.json, assembly_tree.csv, jobs.json}
      — assembly_tree.csv·jobs.json 은 없으면 비어 있는 것으로 본다. 작업의 project_id 는 폴더 이름.
    """
    store.welding_standards = [
        WeldingStandard.model_validate(row) for row in load_standards(seed_dir / "welding_standards.csv")
    ]
    users = _read_json(seed_dir / "users.json")
    store.users = {u["id"]: User.model_validate(u) for u in users["users"]}
    store.current_user_id = users["current_user_id"]

    for ws_dir in _subdirs(seed_dir / "workspaces"):
        ws_id = ws_dir.name
        members = [
            Member.model_validate({**m, **store.users[m["user_id"]].model_dump(include={"name", "email"})})
            for m in _read_json(ws_dir / "members.json")
        ]
        symbols_path = ws_dir / "symbol_dictionary.json"
        symbols = load_symbols(symbols_path) if symbols_path.exists() else []
        store.add_workspace(
            Workspace.model_validate({**_read_json(ws_dir / "workspace.json"), "id": ws_id, "member_count": len(members)}),
            members=members,
            symbols=[SymbolEntry.model_validate(e) for e in symbols],
        )
        for prj_dir in _subdirs(ws_dir / "projects"):
            prj_id = prj_dir.name
            tree_path, jobs_path = prj_dir / "assembly_tree.csv", prj_dir / "jobs.json"
            tree = load_tree(tree_path).values() if tree_path.exists() else []
            jobs = _read_json(jobs_path)["jobs"] if jobs_path.exists() else []
            store.add_project(
                Project.model_validate({**_read_json(prj_dir / "project.json"), "id": prj_id, "workspace_id": ws_id}),
                assembly_tree=[AssemblyNode.model_validate(n) for n in tree],
            )
            for j in jobs:
                store.save_job(Job.model_validate({**j, "workspace_id": ws_id, "project_id": prj_id}))
    return store


def load_db(store: Store, db: DocumentDB, seed_dir: Path = SEED_DIR) -> Store:
    """DB 에 남은 상태를 읽음 (표준 용접 기준만 CSV 에서). 다 읽은 뒤 db 를 붙여 이후 바뀌는 것을 남긴다"""
    store.welding_standards = [
        WeldingStandard.model_validate(row) for row in load_standards(seed_dir / "welding_standards.csv")
    ]
    meta = dict(db.all("meta"))
    store.users = {key: User.model_validate(value) for key, value in db.all("users")}
    store.current_user_id = meta.get("current_user_id")
    for ws_id, value in db.all("workspaces"):
        store.workspaces[ws_id] = Workspace.model_validate(value)
        for table in (store.members, store.symbols, store.projects, store.assembly_trees, store.jobs):
            table[ws_id] = {}
    for key, value in db.all("members"):
        ws_id, user_id = key.split("/", 1)
        store.members[ws_id][user_id] = Member.model_validate(value)
    for key, value in db.all("symbols"):
        ws_id, symbol_id = key.split("/", 1)
        store.symbols[ws_id][symbol_id] = SymbolEntry.model_validate(value)
    trees = dict(db.all("trees"))
    for key, value in db.all("projects"):
        ws_id, project_id = key.split("/", 1)
        store.projects[ws_id][project_id] = Project.model_validate(value)
        store.assembly_trees[ws_id][project_id] = [AssemblyNode.model_validate(n) for n in trees.get(key, [])]
    for key, value in db.all("jobs"):
        ws_id, job_id = key.split("/", 1)
        store.jobs[ws_id][job_id] = Job.model_validate(value)
    for key, value in db.all("images"):
        job_id, _ = key.split("/", 1)
        store.images.setdefault(job_id, []).append(JobImage.model_validate(value))
    store.image_data = db.blobs("image")
    store.preprocessed = db.blobs("preprocessed")
    for key, value in db.all("analyses"):
        store.analyses.setdefault(key.split("/", 1)[0], []).append(value)
    store._db = db
    return store


def open_store(target: DocumentDB | Path | None, seed_dir: Path = SEED_DIR) -> Store:
    """target: DB(open_database) 또는 SQLite 파일 경로. 없으면 메모리만 (시드).
    DB 가 비어 있으면 시드로 채워 저장, 아니면 DB 에서 읽음"""
    if target is None:
        return load_seed(Store(), seed_dir)
    db = Database(target) if isinstance(target, Path) else target
    if db.is_empty():
        store = load_seed(Store(), seed_dir)
        store.attach(db)
        return store
    return load_db(Store(), db, seed_dir)


_store: Store | None = None


def get_store() -> Store:
    """FastAPI 의존성. 처음 호출될 때 DATABASE_URL 의 DB(없으면 시드)로 채운다."""
    global _store
    if _store is None:
        _store = open_store(open_database(os.environ.get("DATABASE_URL")))
    return _store


def reset_store() -> Store:
    """시드 상태로 되돌린다 (테스트마다 호출해 서로 격리 — 파일에 남기지 않음)."""
    global _store
    _store = load_seed(Store())
    return _store
