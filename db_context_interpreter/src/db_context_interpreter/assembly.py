"""c. 조립 경로 DB: 블록 → 대조립 → 중조립 → 소조립 → 부재"""
import re

from db_context_interpreter.ocr_text import ocr_variants
from db_context_interpreter.readings import corrections_by_target, normalize

DEPTH = {"BLOCK": 0, "LARGE": 1, "MID": 2, "SUB": 3, "PART": 4}
PART_LIKE = re.compile(r"^[A-Z]{1,3}-[0-9]+[A-Z]?$")  # 트리에 없어도 부재 번호로 보이는 표기 (예: P-4)
FIXED_PENALTY = 0.9  # 헷갈리는 글자를 고쳐서 맞힌 읽기의 확률 배수
EMPTY_PART = {"node_id": None, "assembly_path": None, "level": None, "found_in_tree": False, "ref_ids": []}


def find_part(readings: list[dict], context_input: dict) -> tuple[dict, list[dict], set[str]]:
    """부재 번호로 보이는 표기를 context_input["assembly_tree"]에서 찾아 Part를 만듦 → (Part, Conflict 목록, 부재 표기로 쓴 읽기 key).
    작업자가 part를 고쳤으면(corrections) 그 조립 경로를 씀. 사진에 부재 표기가 없으면 작업에 적은 조립 경로(job_assembly_path),
    그것도 없으면 빈 Part"""
    tree = context_input["assembly_tree"]
    hits = tree_hits(readings, tree)
    keys = {h["key"] for h in hits}

    correction = corrections_by_target(context_input).get("part")
    if correction:
        path = correction["value"]
        node = next((n for n in tree if n["path"] == path), None)
        return {
            "node_id": node["node_id"] if node else path.rsplit("/", 1)[-1],
            "assembly_path": path,
            "level": node["level"] if node else None,
            "found_in_tree": node is not None,
            "ref_ids": unique(h["ref_id"] for h in hits if on_path(h["node"], path)),
        }, [], keys

    if hits:
        best = max(hits, key=lambda h: (DEPTH[h["node"]["level"]], h["prob"]))
        path = best["node"]["path"]
        same = [h for h in hits if on_path(h["node"], path)]
        others = [h for h in hits if not on_path(h["node"], path)]
        conflicts = []
        if others:
            names = ", ".join(dict.fromkeys(h["node"]["node_id"] for h in [best] + others))
            conflicts.append({
                "type": "ambiguous_reading", "severity": "warning",
                "message": f"조립 트리의 서로 다른 갈래에 있는 부재 표기가 함께 읽힘({names}) — {best['node']['node_id']}로 판단함",
                "ref_ids": unique(h["ref_id"] for h in [best] + others),
            })
        conflicts += [{
            "type": "ambiguous_reading", "severity": "info",
            "message": f"'{h['value']}' 표기를 '{h['fixed']}'로 보정해 조립 트리의 {h['node']['node_id']}로 봄",
            "ref_ids": [h["ref_id"]],
        } for h in same if h["fixed"]]
        node = best["node"]
        return {
            "node_id": node["node_id"], "assembly_path": node["path"], "level": node["level"],
            "found_in_tree": True, "ref_ids": unique(h["ref_id"] for h in same),
        }, conflicts, keys

    for r in readings:
        if r["kind"] == "text" and PART_LIKE.match(normalize(r["value"])):
            return {**EMPTY_PART, "node_id": r["value"], "ref_ids": [r["ref_id"]]}, [{
                "type": "part_not_in_tree", "severity": "error",
                "message": f"부재 표기 '{r['value']}'가 이 프로젝트의 조립 트리에 없음",
                "ref_ids": [r["ref_id"]],
            }], {r["key"]}
    if path := context_input.get("job_assembly_path"):
        return job_part(path, tree)
    return dict(EMPTY_PART), [], keys


def job_part(path: str, tree: list[dict]) -> tuple[dict, list[dict], set[str]]:
    """작업에 적은 조립 경로 → Part (근거 표기 없음). 트리에 없으면 part_not_in_tree"""
    node = next((n for n in tree if n["path"] == path), None)
    part = {
        "node_id": node["node_id"] if node else path.rsplit("/", 1)[-1], "assembly_path": path,
        "level": node["level"] if node else None, "found_in_tree": node is not None, "ref_ids": [],
    }
    conflicts = [] if node else [{
        "type": "part_not_in_tree", "severity": "warning",
        "message": f"작업에 적은 조립 경로 '{path}'가 이 프로젝트의 조립 트리에 없음", "ref_ids": [],
    }]
    return part, conflicts, set()


class TreeIndex:
    """조립 트리 노드를 node_id · 전체 경로로 찾기. 대시를 빠뜨린 읽기(P1 ↔ P-1)도 같은 것으로 봄"""

    def __init__(self, tree: list[dict]) -> None:
        self.index: dict[str, dict] = {}
        for node in tree:
            for key in (node["node_id"], node["path"]):
                self.index.setdefault(normalize(key), node)
                self.index.setdefault(normalize(key).replace("-", ""), node)

    def lookup(self, value: str) -> dict | None:
        key = normalize(value)
        return self.index.get(key) or self.index.get(key.replace("-", ""))

    def lookup_fixed(self, value: str) -> tuple[dict, str | None] | None:
        """(노드, 보정한 읽기 — 그대로 맞으면 None). 그대로 안 맞으면 OCR이 헷갈린 글자를 고쳐 봄 (P-I → P-1)"""
        if node := self.lookup(value):
            return node, None
        return next(((node, v) for v in ocr_variants(value) if (node := self.lookup(v))), None)


def tree_hits(readings: list[dict], tree: list[dict]) -> list[dict]:
    """조립 트리 노드와 같은 표기 → [{ref_id, key, value, fixed, node, prob}].
    바로 읽은 표기(보정 포함)가 하나도 안 맞으면 1단계 후보까지 봄"""
    index = TreeIndex(tree)
    texts = [r for r in readings if r["kind"] == "text"]
    hits = [
        {"ref_id": r["ref_id"], "key": r["key"], "value": r["value"], "fixed": found[1], "node": found[0],
         "prob": r["prob"] * (FIXED_PENALTY if found[1] else 1)}
        for r in texts if (found := index.lookup_fixed(r["value"]))
    ]
    if hits:
        return hits
    return [
        {"ref_id": r["ref_id"], "key": r["key"], "value": r["value"], "fixed": None, "node": node, "prob": prob}
        for r in texts for value, prob in r["candidates"] if (node := index.lookup(value))
    ]


def on_path(node: dict, path: str) -> bool:
    """node가 path의 조상이거나 자기 자신인지"""
    return path == node["path"] or path.startswith(node["path"] + "/")


def unique(items) -> list:
    return list(dict.fromkeys(items))
