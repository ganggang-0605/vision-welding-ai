from pathlib import Path

from app.db.assembly_tree import find_path, load_tree

SEED = Path(__file__).resolve().parents[2] / "data" / "seed" / "assembly_tree.csv"


def test_find_path():
    tree = load_tree(SEED)
    assert find_path(tree, "P-1") == "A1/L1/M2/S1/P-1"
    assert find_path(tree, "nope") is None
