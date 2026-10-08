"""조립 트리 DB (블록→대조립→중조립→소조립→부재)"""
import csv
from pathlib import Path

LEVELS = ["BLOCK", "LARGE", "MID", "SUB", "PART"]


def load_tree(csv_path: Path) -> dict[str, dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return {row["node_id"]: row for row in csv.DictReader(f)}


def find_path(tree: dict[str, dict], node_id: str) -> str | None:
    node = tree.get(node_id)
    return node["path"] if node else None
