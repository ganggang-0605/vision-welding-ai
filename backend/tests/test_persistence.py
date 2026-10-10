"""DB 에 남기기 — 서버를 다시 켜도 워크스페이스 · 작업 · 사진 · 해석 결과가 그대로

같은 테스트를 SQLite(app/db/sqlite.py)와 PostgreSQL(app/db/postgres.py)에서 돌린다.
PostgreSQL 은 TEST_DATABASE_URL 이 있을 때만 (로컬: docker compose up -d db, CI: postgres 서비스) — 테스트마다 스키마를 따로 만들고 지움.
"""
import os
import uuid
from pathlib import Path

import pytest

from app.db.connect import describe, open_database
from app.db.migrate import migrate
from app.db.postgres import PostgresDatabase
from app.db.sqlite import BACKEND_DIR, Database, database_path
from app.schemas import AssemblyNodeCreate, JobCreate, ProjectCreate, SymbolEntryCreate
from app.store import open_store

PG_URL = os.environ.get("TEST_DATABASE_URL", "")
needs_pg = pytest.mark.skipif(not PG_URL, reason="TEST_DATABASE_URL 이 없어 PostgreSQL 테스트 생략")


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=needs_pg)])
def reopen(request, tmp_path):
    """같은 DB 를 다시 여는 함수 (서버 재시작 흉내)"""
    if request.param == "sqlite":
        yield lambda: Database(tmp_path / "vw.db")
        return
    schema = f"test_{uuid.uuid4().hex[:12]}"
    opened: list[PostgresDatabase] = []

    def open_pg():
        opened.append(PostgresDatabase(PG_URL, schema=schema))
        return opened[-1]

    yield open_pg
    if opened:  # 연결에 실패했으면 지울 스키마도 없음
        opened[-1].drop_schema()
    for db in opened:
        db.close()


@pytest.mark.parametrize("url, expected", [
    ("", None),
    ("sqlite:///:memory:", None),
    ("sqlite:///./vision_welding.db  # 주석", BACKEND_DIR / "vision_welding.db"),
    ("sqlite:////tmp/vw.db", Path("/tmp/vw.db")),
])
def test_database_path(url, expected):
    assert database_path(url) == expected


def test_database_path_rejects_other_databases():
    with pytest.raises(ValueError):
        database_path("postgresql://localhost/vw")


def test_open_database_picks_engine(tmp_path):
    assert open_database("") is None
    assert isinstance(open_database(f"sqlite:///{tmp_path}/vw.db  # 주석"), Database)
    with pytest.raises(ValueError):
        open_database("mysql://localhost/vw")


def test_describe_hides_password():
    assert describe("postgresql://vision:secret@localhost:5433/vw") == "PostgreSQL (postgresql://vision:***@localhost:5433/vw)"
    assert describe("") == "메모리 (남기지 않음)"


@needs_pg
def test_open_database_postgres():
    db = open_database(PG_URL)
    assert isinstance(db, PostgresDatabase)
    db.close()


def test_first_start_saves_seed(reopen):
    first = open_store(reopen())
    again = open_store(reopen())
    assert [w.id for w in again.list_workspaces()] == [w.id for w in first.list_workspaces()]
    assert again.get_job("demo", "job_demo_p1") == first.get_job("demo", "job_demo_p1")
    assert again.current_user_id == first.current_user_id
    assert len(again.welding_standards) == 14  # 용접 기준은 늘 CSV 에서


def test_sqlite_path_still_works(tmp_path):
    """예전처럼 SQLite 파일 경로를 넘겨도 됨"""
    path = tmp_path / "vw.db"
    first = open_store(path)
    assert open_store(path).get_job("demo", "job_demo_p1") == first.get_job("demo", "job_demo_p1")


def test_changes_survive_restart(reopen):
    store = open_store(reopen())
    owner = store.default_user()
    workspace = store.create_workspace("2도크", owner, kind="team")
    member = store.invite_member(workspace.id, "새 작업자", "new@example.com")
    project = store.create_project(workspace.id, ProjectCreate(name="B1 블록"))
    entry = store.create_symbol(workspace.id, SymbolEntryCreate(code="F", kind="text", meaning="3F 용접장 각장"))
    removed = store.create_symbol(workspace.id, SymbolEntryCreate(code="X", kind="text", meaning="지울 항목"))
    store.delete_symbol(workspace.id, removed.id)
    store.add_assembly_node(workspace.id, AssemblyNodeCreate(node_id="B1"))
    store.add_assembly_node(workspace.id, AssemblyNodeCreate(node_id="P-1", parent_path="B1", level="PART"))
    job = store.create_job(workspace.id, JobCreate(name="셀 사진", project_id=project.id))
    image = store.add_image(job, "cell.png", "image/png", b"\x89PNG-data", 640, 480)
    store.set_preprocessed(job.id, image.image_id, b"\x89PNG-big")
    store.add_analysis(job.id, {"analysis_id": "an_1", "revision": 1})
    store.add_analysis(job.id, {"analysis_id": "an_2", "revision": 2})
    store.save_job(job.model_copy(update={"status": "needs_review"}))

    again = open_store(reopen())
    assert again.get_workspace(workspace.id).kind == "team" and again.get_workspace(workspace.id).member_count == 2
    assert [m.user_id for m in again.list_members(workspace.id)] == [owner.id, member.user_id]
    assert again.find_user_by_email("new@example.com") is not None
    assert again.list_projects(workspace.id) == [project]
    assert again.list_symbols(workspace.id) == [entry]
    assert [n.path for n in again.get_workspace_assembly_tree(workspace.id)] == ["B1", "B1/P-1"]
    assert again.get_job(workspace.id, job.id).status == "needs_review"
    (stored,) = again.list_images(job.id)
    assert stored.preprocessed is True and again.get_image(job.id, image.image_id)[1] == b"\x89PNG-data"
    assert again.get_preprocessed(image.image_id) == b"\x89PNG-big"
    assert [a["analysis_id"] for a in again.list_analyses(job.id)] == ["an_1", "an_2"]
    # 시드 워크스페이스 순서 다음에 새로 만든 것
    assert [w.id for w in again.list_workspaces()][-1] == workspace.id


def test_memory_store_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = open_store(None)
    store.create_workspace("임시", store.default_user())
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("target", ["sqlite", pytest.param("postgres", marks=needs_pg)])
def test_migrate_sqlite_to_other(tmp_path, target):
    """쓰던 SQLite 파일 → 다른 DB 로 옮겨도 같은 상태 (app/db/migrate.py)"""
    source_db = Database(tmp_path / "old.db")
    store = open_store(source_db)
    job = store.create_job("demo", JobCreate(name="옮길 작업", project_id="block_a1"))
    image = store.add_image(job, "cell.png", "image/png", b"\x89PNG-data", 640, 480)
    store.add_analysis(job.id, {"analysis_id": "an_1", "revision": 1})

    schema = f"test_{uuid.uuid4().hex[:12]}"
    target_db = Database(tmp_path / "new.db") if target == "sqlite" else PostgresDatabase(PG_URL, schema=schema)
    try:
        docs, blobs = migrate(source_db, target_db)
        assert docs == len(source_db.rows()) and blobs == 1
        moved = open_store(target_db)
        assert [w.id for w in moved.list_workspaces()] == [w.id for w in store.list_workspaces()]
        assert moved.get_job("demo", job.id) == store.get_job("demo", job.id)
        assert moved.get_image(job.id, image.image_id)[1] == b"\x89PNG-data"
        assert [a["analysis_id"] for a in moved.list_analyses(job.id)] == ["an_1"]
        with pytest.raises(ValueError):  # 비어 있지 않으면 덮어쓰지 않음
            migrate(source_db, target_db)
    finally:
        if target == "postgres":
            target_db.drop_schema()
        target_db.close()
        source_db.close()
