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


def test_workspace_assembly_tree(client):
    """조립 경로 사전은 워크스페이스에 하나 — 블록별로 나눠 저장된 트리를 합친 것 (트리가 빈 워크스페이스는 빈 목록)"""
    nodes = client.get("/workspaces/demo/assembly-tree").json()
    assert [n["node_id"] for n in nodes] == ["A1", "L1", "M2", "S1", "S2", "P-1", "P-2", "P-3"]
    assert client.get("/workspaces/personal/assembly-tree").json() == []
    assert client.get("/workspaces/nope/assembly-tree").status_code == 404


def test_add_assembly_nodes_to_empty_workspace(client):
    """새 워크스페이스도 조립 경로를 채울 수 있음 — 단계는 상위 노드의 바로 아래, 최상위는 블록"""
    url = "/workspaces/personal/assembly-tree"
    res = client.post(url, json={"node_id": "B1"})
    assert res.status_code == 201
    assert res.json() == {"node_id": "B1", "parent_id": None, "level": "BLOCK", "path": "B1"}
    assert client.post(url, json={"node_id": "L1", "parent_path": "B1"}).json()["level"] == "LARGE"
    part = client.post(url, json={"node_id": "P-9", "parent_path": "B1/L1", "level": "PART"}).json()
    assert part == {"node_id": "P-9", "parent_id": "L1", "level": "PART", "path": "B1/L1/P-9"}
    assert [n["path"] for n in client.get(url).json()] == ["B1", "B1/L1", "B1/L1/P-9"]


def test_add_assembly_node_goes_to_the_parents_block(client):
    client.post("/workspaces/demo/assembly-tree", json={"node_id": "P-4", "parent_path": "A1/L1/M2/S2"})
    assert client.get(f"{PROJECTS}/block_a1/assembly-tree").json()[-1]["path"] == "A1/L1/M2/S2/P-4"


def test_add_assembly_node_rejected(client):
    url = "/workspaces/demo/assembly-tree"
    assert client.post(url, json={"node_id": "S1", "parent_path": "A1/L1/M2"}).status_code == 409
    assert client.post(url, json={"node_id": "X", "parent_path": "Z9"}).status_code == 422
    assert client.post(url, json={"node_id": "X", "parent_path": "A1/L1/M2/S1/P-1"}).status_code == 422
    assert client.post(url, json={"node_id": "X", "parent_path": "A1/L1", "level": "LARGE"}).status_code == 422
    assert client.post(url, json={"node_id": "a/b"}).status_code == 422
    assert client.post(url, json={"node_id": " "}).status_code == 422
    assert client.post("/workspaces/nope/assembly-tree", json={"node_id": "X"}).status_code == 404


def test_delete_assembly_node(client):
    url = "/workspaces/demo/assembly-tree"
    assert client.delete(f"{url}/A1/L1/M2/S2").status_code == 409  # 아래에 P-3
    assert client.delete(f"{url}/A1/L1/M2/S2/P-3").status_code == 204
    assert client.delete(f"{url}/A1/L1/M2/S2").status_code == 204
    assert client.delete(f"{url}/A1/L1/M2/S2").status_code == 404
    assert "A1/L1/M2/S2" not in [n["path"] for n in client.get(url).json()]

