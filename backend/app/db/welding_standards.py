"""표준 용접 기준 DB — 모든 워크스페이스가 공유하는 공식 기준 (읽기 전용, welding_standards.csv)"""
import csv
from pathlib import Path


def load_standards(csv_path: Path) -> list[dict]:
    """빈 칸(판 두께 없이 각장별 값만 있는 행, 각장이 없는 행)은 None"""
    with open(csv_path, newline="", encoding="utf-8") as f:
        return [{key: value or None for key, value in row.items()} for row in csv.DictReader(f)]
