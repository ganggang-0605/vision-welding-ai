from pathlib import Path

from app.db.assembly_tree import find_path, load_tree

SEED = Path(__file__).resolve().parents[2] / "data" / "seed" / "workspaces" / "demo" / "assembly_tree.csv"


def test_find_path():
    tree = load_tree(SEED)
    assert find_path(tree, "P-1") == "A1/L1/M2/S1/P-1"
    assert find_path(tree, "nope") is None
    assert tree["A1"]["parent_id"] is None
    assert tree["P-1"]["parent_id"] == "S1"


def test_assembly_tree_api(client):
    res = client.get("/workspaces/demo/assembly-tree")
    assert res.status_code == 200
    nodes = res.json()
    assert [n["node_id"] for n in nodes] == ["A1", "L1", "M2", "S1", "S2", "P-1", "P-2", "P-3"]
    assert nodes[0] == {"node_id": "A1", "parent_id": None, "level": "BLOCK", "path": "A1"}
    assert nodes[-1] == {"node_id": "P-3", "parent_id": "S2", "level": "PART", "path": "A1/L1/M2/S2/P-3"}
