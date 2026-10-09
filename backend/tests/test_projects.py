"""프로젝트(블록) — 워크스페이스 안의 블록. 조립 트리·작업이 프로젝트에 속한다."""
from datetime import datetime

import pytest

PROJECTS = "/workspaces/demo/projects"
PROJECT_KEYS = {"id", "workspace_id", "name", "description", "created_at"}


def test_seed_projects(client):
    projects = client.get(PROJECTS).json()
    assert all(set(p) == PROJECT_KEYS for p in projects)
    assert [(p["id"], p["workspace_id"], p["name"]) for p in projects] == [
        ("block_a1", "demo", "A1 블록"), ("block_a2", "demo", "A2 블록"),
    ]
    [practice] = client.get("/workspaces/personal/projects").json()
    assert (practice["id"], practice["name"], practice["description"]) == ("practice", "연습용 블록", None)


def test_create_and_get_project(client):
    res = client.post(PROJECTS, json={"name": "  A3 블록 ", "description": "신조선"})
    assert res.status_code == 201
    project = res.json()
    assert set(project) == PROJECT_KEYS
    assert project["id"].startswith("prj_")
    assert (project["workspace_id"], project["name"], project["description"]) == ("demo", "A3 블록", "신조선")
    assert datetime.fromisoformat(project["created_at"]).tzinfo is not None

    assert client.get(f"{PROJECTS}/{project['id']}").json() == project
    assert client.get(PROJECTS).json()[-1] == project  # 생성 순 (오래된 것부터)
    assert client.get(f"{PROJECTS}/{project['id']}/assembly-tree").json() == []
    assert client.get("/workspaces/demo/jobs", params={"project_id": project["id"]}).json() == []
    # 다른 워크스페이스에는 보이지 않는다
    assert project not in client.get("/workspaces/personal/projects").json()


def test_create_project_without_description(client):
    assert client.post(PROJECTS, json={"name": "A4 블록"}).json()["description"] is None


@pytest.mark.parametrize("body", [{}, {"name": ""}, {"name": "   "}, {"name": None}, {"name": "x" * 101}])
def test_create_project_validation(client, body):
    assert client.post(PROJECTS, json=body).status_code == 422
    assert len(client.get(PROJECTS).json()) == 2


@pytest.mark.parametrize("path", [
    "/workspaces/personal/projects/block_a1",               # 다른 워크스페이스의 프로젝트
    "/workspaces/personal/projects/block_a1/assembly-tree",
    "/workspaces/demo/projects/practice",
    "/workspaces/demo/projects/nope",
    "/workspaces/demo/projects/nope/assembly-tree",
])
def test_project_not_found(client, path):
    res = client.get(path)
    assert res.status_code == 404
    assert "프로젝트" in res.json()["detail"]


def test_project_from_other_workspace_by_new_id(client):
    other = client.post("/workspaces", json={"name": "다른 조선소"}).json()["id"]
    project = client.post(f"/workspaces/{other}/projects", json={"name": "Z1 블록"}).json()
    assert project["workspace_id"] == other
    assert client.get(f"{PROJECTS}/{project['id']}").status_code == 404
