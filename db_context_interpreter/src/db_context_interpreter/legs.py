"""e. PAC 과제 결과: 수기 각장(F·V·S + mm)과 셀 좌·우 끝 형태(slit · slot · collar_front · collar_back · scallop)

둘 다 사전 대조 결과(DictionaryMatch)에서 뽑음 — 각장은 사전의 각장 코드 + 숫자, 셀 형태는 사전 code가 셀 형태인 기호.
작업자가 leg_lengths · cell을 고쳤으면(corrections) 그 값.
"""
from db_context_interpreter.dictionary import CODE_VALUE, Dictionary, is_leg_entry
from db_context_interpreter.readings import corrections_by_target, normalize

# shared/schemas/common.schema.json CellFeature (= backend/app/schemas.py CellFeature), 표시 순서
CELL_FEATURES = ("slit", "slot", "collar_front", "collar_back", "scallop")


def leg_meaning(entry: dict | None) -> str | None:
    """사전 뜻에서 숫자 설명을 뺀 것 ("3F 용접장 각장 (뒤의 숫자가 각장 mm)" → "3F 용접장 각장")"""
    return entry["meaning"].partition("(")[0].strip() if entry else None


def find_leg_lengths(pairs: list[tuple[dict, dict]], context_input: dict) -> list[dict]:
    """[(읽기, DictionaryMatch)] → LegLength 목록 (읽는 순서). 숫자 없이 코드만 있는 표기(V)는 크기를 몰라 뺌"""
    dictionary = Dictionary(context_input["symbols"])
    correction = corrections_by_target(context_input).get("leg_lengths")
    if correction:
        return [{
            "code": leg["code"], "size_mm": leg["size_mm"], "raw_text": leg["raw_text"],
            "meaning": leg_meaning(dictionary.by_code.get(leg["code"])), "ref_ids": [],
        } for leg in correction["value"]]

    legs = []
    for _, m in pairs:
        entry = dictionary.by_code.get(m["code"])
        found = CODE_VALUE.match(normalize(m["raw"]))
        if not entry or not is_leg_entry(entry) or not found or m["match"] == "none":
            continue
        legs.append({
            "code": entry["code"], "size_mm": float(found.group(2)), "raw_text": normalize(m["raw"]),
            "meaning": leg_meaning(entry), "ref_ids": m["ref_ids"],
        })
    return legs


def find_cell(pairs: list[tuple[dict, dict]], context_input: dict, vision_result: dict,
              vlm_result: dict | None) -> tuple[dict | None, list[dict]]:
    """셀 형태 기호를 사진 가운데를 기준으로 왼쪽 · 오른쪽 끝으로 나눔 → (Cell | None, Conflict 목록).
    위치(bbox)를 모르는 셀 형태 기호는 좌·우를 정할 수 없어 작업자 확인. 셀 형태 기호가 없으면 None"""
    correction = corrections_by_target(context_input).get("cell")
    if correction:
        return {"left": list(correction["value"]["left"]), "right": list(correction["value"]["right"]), "ref_ids": []}, []

    boxes = {d["id"]: d["bbox"] for d in vision_result["symbols"]}
    if vlm_result:
        boxes |= {x["ref_id"]: x["bbox"] for x in vlm_result["reading"]["symbols"] if "bbox" in x}
    middle = vision_result["image_size"]["width"] / 2
    sides: dict[str, set[str]] = {"left": set(), "right": set()}
    refs, unplaced = [], []
    for r, m in pairs:
        if r["kind"] != "symbol" or m["code"] not in CELL_FEATURES:
            continue
        bbox = boxes.get(r["ref_id"])
        if bbox is None:
            unplaced.append((r["ref_id"], m["code"]))
            continue
        sides["left" if (bbox[0] + bbox[2]) / 2 < middle else "right"].add(m["code"])
        refs.append(r["ref_id"])
    conflicts = [{
        "type": "ambiguous_reading", "severity": "warning",
        "message": f"셀 형태 '{code}'의 위치를 몰라 왼쪽·오른쪽 끝 중 어디인지 정하지 못함", "ref_ids": [ref],
    } for ref, code in unplaced]
    if not refs:
        return None, conflicts
    return {
        "left": [f for f in CELL_FEATURES if f in sides["left"]],
        "right": [f for f in CELL_FEATURES if f in sides["right"]],
        "ref_ids": list(dict.fromkeys(refs)),
    }, conflicts
