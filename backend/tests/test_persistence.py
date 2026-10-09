"""SQLite 파일에 남기기 (app/db/sqlite.py) — 서버를 다시 켜도 워크스페이스 · 작업 · 사진 · 해석 결과가 그대로"""
from pathlib import Path

import pytest

from app.db.sqlite import BACKEND_DIR, database_path
from app.schemas import JobCreate, ProjectCreate, SymbolEntryCreate
from app.store import open_store


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


def test_first_start_saves_seed(tmp_path):
    path = tmp_path / "vw.db"
    first = open_store(path)
    again = open_store(path)
    assert [w.id for w in again.list_workspaces()] == [w.id for w in first.list_workspaces()]
    assert again.get_job("demo", "job_demo_p1") == first.get_job("demo", "job_demo_p1")
    assert again.current_user_id == first.current_user_id
    assert len(again.welding_standards) == 14  # 용접 기준은 늘 CSV 에서


def test_changes_survive_restart(tmp_path):
    path = tmp_path / "vw.db"
    store = open_store(path)
    owner = store.default_user()
    workspace = store.create_workspace("2도크", owner, kind="team")
    member = store.invite_member(workspace.id, "새 작업자", "new@example.com")
    project = store.create_project(workspace.id, ProjectCreate(name="B1 블록"))
    entry = store.create_symbol(workspace.id, SymbolEntryCreate(code="F", kind="text", meaning="3F 용접장 각장"))
    removed = store.create_symbol(workspace.id, SymbolEntryCreate(code="X", kind="text", meaning="지울 항목"))
    store.delete_symbol(workspace.id, removed.id)
    job = store.create_job(workspace.id, JobCreate(name="셀 사진", project_id=project.id))
    image = store.add_image(job, "cell.png", "image/png", b"\x89PNG-data", 640, 480)
    store.set_preprocessed(job.id, image.image_id, b"\x89PNG-big")
    store.add_analysis(job.id, {"analysis_id": "an_1", "revision": 1})
    store.add_analysis(job.id, {"analysis_id": "an_2", "revision": 2})
    store.save_job(job.model_copy(update={"status": "needs_review"}))

    again = open_store(path)
    assert again.get_workspace(workspace.id).kind == "team" and again.get_workspace(workspace.id).member_count == 2
    assert [m.user_id for m in again.list_members(workspace.id)] == [owner.id, member.user_id]
    assert again.find_user_by_email("new@example.com") is not None
    assert again.list_projects(workspace.id) == [project]
    assert again.list_symbols(workspace.id) == [entry]
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
