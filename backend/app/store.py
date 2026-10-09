"""임시 인메모리 저장소 (워크스페이스 단위)

⚠️ 실제 DB 로 교체하기 전까지 쓰는 임시 구현이다. 데이터는 프로세스 메모리에만 있어
서버를 재시작하면 data/seed 의 초기 상태(팀 워크스페이스 "demo", 개인 워크스페이스 "personal")로 돌아간다.
TODO: SQLAlchemy(requirements 에 포함) 기반 DB 로 교체 — 라우터는 Store 메서드만 쓰므로 이 모듈만 바꾸면 된다.
TODO(인증): 로그인 없음 — 요청 헤더 X-User-Id 가 데모 사용자를 고르고(없으면 시드의 current_user_id),
  워크스페이스 목록만 그 사용자가 멤버인 것으로 거른다. 그 밖의 권한 검사는 없어 누구나 모든 워크스페이스에 접근할 수 있다.

- 워크스페이스별 데이터(멤버, 문자/기호 사전, 프로젝트, 작업)는 workspace_id 를 키로 하는 dict 에 둔다.
- 조립 트리는 프로젝트(블록)별 — assembly_trees[workspace_id][project_id]. 작업은 project_id 필드로 프로젝트에 속한다.
- 사용자와 표준 용접 기준은 모든 워크스페이스가 공유하는 공통 데이터다 (용접 기준은 읽기 전용).
- 확인 후 변경하는 작업(승인, 사전 항목 수정·삭제, 워크스페이스 수정, 멤버 초대)은 잠금 안에서 최신 상태를
  다시 읽어 처리한다 — 동시 요청이 같은 스냅샷을 보고 둘 다 성공하지 않도록.
  (DB 로 바꾸면 조건부 UPDATE·행 잠금·유니크 제약으로 대체)
"""
import json
import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.db.assembly_tree import load_tree
from app.db.symbol_dictionary import load_symbols
from app.db.welding_standards import load_standards
from app.schemas import (
    AssemblyNode,
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

# 승인할 수 있는 작업 상태
APPROVABLE: frozenset[JobStatus] = frozenset({"awaiting_approval", "needs_review"})


class JobStatusConflict(Exception):
    """현재 상태에서는 할 수 없는 작업 상태 변경 (API 에서는 409)"""

    def __init__(self, status: JobStatus) -> None:
        super().__init__(status)
        self.status = status


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


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(UTC)


class Store:
    def __init__(self) -> None:
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
        self.analyses: dict[str, list[dict]] = {}
        self.welding_standards: list[WeldingStandard] = []
        self._lock = threading.RLock()

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
            member = Member(user_id=user.id, name=user.name, email=user.email, role="member", joined_at=utcnow())
            members[user.id] = member
            self.workspaces[workspace_id] = self.workspaces[workspace_id].model_copy(
                update={"kind": "team", "member_count": len(members)}
            )
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
            return self.symbols[workspace_id].pop(symbol_id, None) is not None

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
        return project

    def create_project(self, workspace_id: str, data: ProjectCreate) -> Project:
        """새 프로젝트 — 조립 트리는 비어 있다."""
        return self.add_project(
            Project(id=new_id("prj"), workspace_id=workspace_id, created_at=utcnow(), **data.model_dump())
        )

    # ── 조립 트리 ──
    def get_assembly_tree(self, workspace_id: str, project_id: str) -> list[AssemblyNode]:
        return list(self.assembly_trees[workspace_id][project_id])

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
        return job

    def approve_job(self, workspace_id: str, job_id: str, approved_by: str) -> Job | None:
        """승인 대기·검토 필요 상태만 승인한다 (아니면 JobStatusConflict). 없는 작업이면 None.

        상태 확인과 저장을 한 잠금 안에서 해 동시에 여러 번 승인해도 하나만 성공한다.
        """
        with self._lock:
            job = self.get_job(workspace_id, job_id)
            if job is None:
                return None
            if job.status not in APPROVABLE:
                raise JobStatusConflict(job.status)
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
        return image

    def list_images(self, job_id: str) -> list[JobImage]:
        """올린 순서 (가장 최근이 마지막)"""
        return list(self.images.get(job_id, []))

    def get_image(self, job_id: str, image_id: str) -> tuple[JobImage, bytes] | None:
        image = next((i for i in self.images.get(job_id, []) if i.image_id == image_id), None)
        return (image, self.image_data[image_id]) if image else None

    def add_analysis(self, job_id: str, analysis: dict) -> dict:
        with self._lock:
            self.analyses.setdefault(job_id, []).append(analysis)
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


_store: Store | None = None


def get_store() -> Store:
    """FastAPI 의존성. 처음 호출될 때 시드 데이터로 채운다."""
    global _store
    if _store is None:
        _store = load_seed(Store())
    return _store


def reset_store() -> Store:
    """시드 상태로 되돌린다 (테스트마다 호출해 서로 격리)."""
    global _store
    _store = load_seed(Store())
    return _store
