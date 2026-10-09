"""c. 조립 경로 DB: 블록 → 대조립 → 중조립 → 소조립 → 부재"""
import re

from db_context_interpreter.readings import corrections_by_target, normalize

DEPTH = {"BLOCK": 0, "LARGE": 1, "MID": 2, "SUB": 3, "PART": 4}
PART_LIKE = re.compile(r"^[A-Z]{1,3}-[0-9]+[A-Z]?$")  # 트리에 없어도 부재 번호로 보이는 표기 (예: P-4)
EMPTY_PART = {"node_id": None, "assembly_path": None, "level": None, "found_in_tree": False, "ref_ids": []}


def find_part(readings: list[dict], context_input: dict) -> tuple[dict, list[dict]]:
    """부재 번호로 보이는 표기를 context_input["assembly_tree"]에서 찾아 Part를 만듦 → (Part, Conflict 목록).
    작업자가 part를 고쳤으면(corrections) 그 조립 경로를 씀. 못 찾으면 빈 Part"""
    tree = context_input["assembly_tree"]
    hits = tree_hits(readings, tree)

    correction = corrections_by_target(context_input).get("part")
    if correction:
        path = correction["value"]
        node = next((n for n in tree if n["path"] == path), None)
        return {
            "node_id": node["node_id"] if node else path.rsplit("/", 1)[-1],
            "assembly_path": path,
            "level": node["level"] if node else None,
            "found_in_tree": node is not None,
            "ref_ids": [h["ref_id"] for h in hits if on_path(h["node"], path)],
        }, []

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
        node = best["node"]
        return {
            "node_id": node["node_id"], "assembly_path": node["path"], "level": node["level"],
            "found_in_tree": True, "ref_ids": unique(h["ref_id"] for h in same),
        }, conflicts

    for r in readings:
        if r["kind"] == "text" and PART_LIKE.match(normalize(r["value"])):
            return {**EMPTY_PART, "node_id": r["value"], "ref_ids": [r["ref_id"]]}, [{
                "type": "part_not_in_tree", "severity": "error",
                "message": f"부재 표기 '{r['value']}'가 이 프로젝트의 조립 트리에 없음",
                "ref_ids": [r["ref_id"]],
            }]
    return dict(EMPTY_PART), []


def tree_hits(readings: list[dict], tree: list[dict]) -> list[dict]:
    """조립 트리 노드(node_id 또는 전체 경로)와 같은 표기 → [{ref_id, node, prob}].
    대시를 빠뜨린 읽기(P1 ↔ P-1)도 같은 것으로 봄. 바로 읽은 표기가 하나도 안 맞으면 1단계 후보까지 봄"""
    index: dict[str, dict] = {}
    for node in tree:
        for key in (node["node_id"], node["path"]):
            index.setdefault(normalize(key), node)
            index.setdefault(normalize(key).replace("-", ""), node)

    def lookup(value: str) -> dict | None:
        key = normalize(value)
        return index.get(key) or index.get(key.replace("-", ""))

    texts = [r for r in readings if r["kind"] == "text"]
    hits = [{"ref_id": r["ref_id"], "node": node, "prob": r["prob"]} for r in texts if (node := lookup(r["value"]))]
    if hits:
        return hits
    return [
        {"ref_id": r["ref_id"], "node": node, "prob": prob}
        for r in texts for value, prob in r["candidates"] if (node := lookup(value))
    ]


def on_path(node: dict, path: str) -> bool:
    """node가 path의 조상이거나 자기 자신인지"""
    return path == node["path"] or path.startswith(node["path"] + "/")


def unique(items) -> list:
    return list(dict.fromkeys(items))
