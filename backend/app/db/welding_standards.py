"""표준 용접 기준 DB — 모든 워크스페이스가 공유하는 공식 기준 (읽기 전용, welding_standards.csv)"""
import csv
from pathlib import Path


def load_standards(csv_path: Path) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
