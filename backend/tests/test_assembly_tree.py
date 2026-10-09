from pathlib import Path

from app.db.assembly_tree import find_path, load_tree

SEED = (
    Path(__file__).resolve().parents[2]
    / "data" / "seed" / "workspaces" / "demo" / "projects" / "block_a1" / "assembly_tree.csv"
)
PROJECTS = "/workspaces/demo/projects"


def test_find_path():
    tree = load_tree(SEED)
    assert find_path(tree, "P-1") == "A1/L1/M2/S1/P-1"
    assert find_path(tree, "nope") is None
    assert tree["A1"]["parent_id"] is None
    assert tree["P-1"]["parent_id"] == "S1"


def test_assembly_tree_api(client):
    res = client.get(f"{PROJECTS}/block_a1/assembly-tree")
    assert res.status_code == 200
    nodes = res.json()
    assert [n["node_id"] for n in nodes] == ["A1", "L1", "M2", "S1", "S2", "P-1", "P-2", "P-3"]
    assert nodes[0] == {"node_id": "A1", "parent_id": None, "level": "BLOCK", "path": "A1"}
    assert nodes[-1] == {"node_id": "P-3", "parent_id": "S2", "level": "PART", "path": "A1/L1/M2/S2/P-3"}


def test_assembly_tree_per_project(client):
    """조립 트리는 프로젝트(블록)별 — 트리 파일이 없는 시드 프로젝트·새 프로젝트는 빈 트리"""
    assert client.get(f"{PROJECTS}/block_a2/assembly-tree").json() == []
    assert client.get("/workspaces/personal/projects/practice/assembly-tree").json() == []
    project = client.post(PROJECTS, json={"name": "A3 블록"}).json()
    assert client.get(f"{PROJECTS}/{project['id']}/assembly-tree").json() == []


def test_workspace_assembly_tree_route_removed(client):
    """예전 워크스페이스 단위 경로는 없다 — 프로젝트 하위로 이동"""
    assert client.get("/workspaces/demo/assembly-tree").status_code == 404
