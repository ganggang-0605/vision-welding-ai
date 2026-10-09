"""문자/기호 사전 DB — 워크스페이스별 symbol_dictionary.json ({"entries": [SymbolEntry, ...]})"""
import json
from pathlib import Path


def load_symbols(json_path: Path) -> list[dict]:
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)["entries"]
