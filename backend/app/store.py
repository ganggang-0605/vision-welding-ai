"""임시 인메모리 저장소 (워크스페이스 단위)

⚠️ 실제 DB 로 교체하기 전까지 쓰는 임시 구현이다. 데이터는 프로세스 메모리에만 있어
서버를 재시작하면 data/seed 의 초기 상태(데모 워크스페이스 "demo")로 돌아간다.
TODO: SQLAlchemy(requirements 에 포함) 기반 DB 로 교체 — 라우터는 Store 메서드만 쓰므로 이 모듈만 바꾸면 된다.
TODO: 인증·멤버 관리 없음 — 지금은 누구나 모든 워크스페이스에 접근할 수 있다.

- 워크스페이스별 데이터(문자/기호 사전, 조립 트리, 작업)는 workspace_id 를 키로 하는 dict 에 둔다.
- 표준 용접 기준은 모든 워크스페이스가 공유하는 공통 데이터(읽기 전용)다.
- 확인 후 변경하는 작업(승인, 사전 항목 수정·삭제)은 잠금 안에서 최신 상태를 다시 읽어 처리한다 —
  동시 요청이 같은 스냅샷을 보고 둘 다 성공하지 않도록. (DB 로 바꾸면 조건부 UPDATE·행 잠금으로 대체)
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
    JobStatus,
    SymbolEntry,
    SymbolEntryCreate,
    WeldingStandard,
    Workspace,
)

SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seed"

# 승인할 수 있는 작업 상태
APPROVABLE: frozenset[JobStatus] = frozenset({"awaiting_approval", "needs_review"})


class JobStatusConflict(Exception):
    """현재 상태에서는 할 수 없는 작업 상태 변경 (API 에서는 409)"""

    def __init__(self, status: JobStatus) -> None:
        super().__init__(status)
        self.status = status


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(UTC)


class Store:
    def __init__(self) -> None:
        self.workspaces: dict[str, Workspace] = {}
        self.symbols: dict[str, dict[str, SymbolEntry]] = {}
        self.assembly_trees: dict[str, list[AssemblyNode]] = {}
        self.jobs: dict[str, dict[str, Job]] = {}
        self.welding_standards: list[WeldingStandard] = []
        self._lock = threading.RLock()

    # ── 워크스페이스 ──
    def list_workspaces(self) -> list[Workspace]:
        return list(self.workspaces.values())

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        return self.workspaces.get(workspace_id)

    def add_workspace(
        self,
        workspace: Workspace,
        symbols: Iterable[SymbolEntry] = (),
        assembly_tree: Iterable[AssemblyNode] = (),
        jobs: Iterable[Job] = (),
    ) -> Workspace:
        self.workspaces[workspace.id] = workspace
        self.symbols[workspace.id] = {s.id: s for s in symbols}
        self.assembly_trees[workspace.id] = list(assembly_tree)
        self.jobs[workspace.id] = {j.id: j for j in jobs}
        return workspace

    def create_workspace(
        self, name: str, description: str | None = None, copy_symbols_from: str | None = None
    ) -> Workspace:
        """새 워크스페이스. copy_symbols_from 이 있으면 그 워크스페이스의 사전을 새 id 로 복제한다."""
        symbols = [
            s.model_copy(update={"id": new_id("sym")}, deep=True)
            for s in (self.list_symbols(copy_symbols_from) if copy_symbols_from else [])
        ]
        workspace = Workspace(id=new_id("ws"), name=name, description=description, created_at=utcnow())
        return self.add_workspace(workspace, symbols=symbols)

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

    # ── 조립 트리 ──
    def get_assembly_tree(self, workspace_id: str) -> list[AssemblyNode]:
        return list(self.assembly_trees[workspace_id])

    # ── 작업 ──
    def list_jobs(self, workspace_id: str, q: str | None = None, status: JobStatus | None = None) -> list[Job]:
        """작업 DB 검색. q 는 이름·조립 경로·표기 원문/해석에서 대소문자 무시 부분 일치. 최신순."""
        jobs = list(self.jobs[workspace_id].values())
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


def _searchable(job: Job) -> list[str]:
    texts = [job.name, job.assembly_path or ""]
    if job.marking:
        texts += [job.marking.raw_text, job.marking.interpretation]
    return texts


def _read_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_seed(store: Store, seed_dir: Path = SEED_DIR) -> Store:
    """data/seed 를 읽어 공통 용접 기준과 시드 워크스페이스(데모)를 채운다.

    워크스페이스 시드: workspaces/<workspace_id>/{workspace.json, symbol_dictionary.json, assembly_tree.csv, jobs.json}
    """
    store.welding_standards = [
        WeldingStandard.model_validate(row) for row in load_standards(seed_dir / "welding_standards.csv")
    ]
    for ws_dir in sorted(p for p in (seed_dir / "workspaces").iterdir() if p.is_dir()):
        ws_id = ws_dir.name
        store.add_workspace(
            Workspace.model_validate({**_read_json(ws_dir / "workspace.json"), "id": ws_id}),
            symbols=[SymbolEntry.model_validate(e) for e in load_symbols(ws_dir / "symbol_dictionary.json")],
            assembly_tree=[AssemblyNode.model_validate(n) for n in load_tree(ws_dir / "assembly_tree.csv").values()],
            jobs=[
                Job.model_validate({**j, "workspace_id": ws_id})
                for j in _read_json(ws_dir / "jobs.json")["jobs"]
            ],
        )
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
