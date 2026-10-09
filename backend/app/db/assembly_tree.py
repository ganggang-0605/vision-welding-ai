"""조립 트리 DB (블록→대조립→중조립→소조립→부재) — 프로젝트(호선)별 assembly_tree.csv"""
import csv
from pathlib import Path

LEVELS = ["BLOCK", "LARGE", "MID", "SUB", "PART"]


def load_tree(csv_path: Path) -> dict[str, dict]:
    """node_id → 행 (CSV 순서 유지). 최상위 노드의 빈 parent_id 는 None."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        return {row["node_id"]: {**row, "parent_id": row["parent_id"] or None} for row in csv.DictReader(f)}


def find_path(tree: dict[str, dict], node_id: str) -> str | None:
    node = tree.get(node_id)
    return node["path"] if node else None
