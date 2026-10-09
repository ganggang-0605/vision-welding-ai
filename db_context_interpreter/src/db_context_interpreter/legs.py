"""e. PAC 과제 결과: 수기 각장(F·V·S + mm)과 셀 좌·우 끝 형태(slit · slot · collar_front · collar_back · scallop)

둘 다 사전 대조 결과(DictionaryMatch)에서 뽑음 — 각장은 사전의 각장 코드 + 숫자, 셀 형태는 사전 code가 셀 형태인 기호.
작업자가 leg_lengths · cell을 고쳤으면(corrections) 그 값.
"""
import re

from db_context_interpreter.dictionary import CODE_VALUE, Dictionary, is_leg_entry
from db_context_interpreter.readings import corrections_by_target, normalize

# shared/schemas/common.schema.json CellFeature (= backend/app/schemas.py CellFeature), 표시 순서
CELL_FEATURES = ("slit", "slot", "collar_front", "collar_back", "scallop")
VLM_CODE_VALUE = re.compile(r"([A-Z]+)([0-9]+(?:\.[0-9]+)?)")  # VLM 글자 속 코드 + 숫자 (줄 안 어디든)


def leg_meaning(entry: dict | None) -> str | None:
    """사전 뜻에서 숫자 설명을 뺀 것 ("3F 용접장 각장 (뒤의 숫자가 각장 mm)" → "3F 용접장 각장")"""
    return entry["meaning"].partition("(")[0].strip() if entry else None


def find_leg_lengths(pairs: list[tuple[dict, dict]], context_input: dict,
                     vlm_result: dict | None = None) -> tuple[list[dict], list[dict]]:
    """[(읽기, DictionaryMatch)] → (LegLength 목록 (읽는 순서), Conflict 목록). 숫자 없이 코드만 있는 표기(V)는 크기를 몰라 뺌.
    사진을 본 VLM이 있으면 1단계만 읽은 각장은 VLM 읽기에도 있어야 씀 — 각장 위주로 학습한 인식기가 치수(418)를
    각장(F11.8)으로 지어내는 일이 있어서. 없으면 각장에서 빼고 작업자 확인 (VLM이 없으면 확인할 길이 없어 그대로 씀)"""
    dictionary = Dictionary(context_input["symbols"])
    correction = corrections_by_target(context_input).get("leg_lengths")
    if correction:
        return [{
            "code": leg["code"], "size_mm": leg["size_mm"], "raw_text": leg["raw_text"],
            "meaning": leg_meaning(dictionary.by_code.get(leg["code"])), "ref_ids": [],
        } for leg in correction["value"]], []

    seen_by_vlm = vlm_texts(vlm_result)
    legs, conflicts = [], []
    for r, m in pairs:
        entry = dictionary.by_code.get(m["code"])
        found = CODE_VALUE.match(normalize(m["raw"]))
        if not entry or not is_leg_entry(entry) or not found or m["match"] == "none":
            continue
        raw = normalize(m["raw"])
        if seen_by_vlm is not None and ocr_only(r) and (entry["code"], float(found.group(2))) not in seen_by_vlm:
            conflicts.append({
                "type": "ocr_vlm_mismatch", "severity": "warning",
                "message": f"1단계만 읽은 각장 '{raw}'를 사진을 본 VLM은 읽지 않아 각장으로 쓰지 않음", "ref_ids": m["ref_ids"],
            })
            continue
        legs.append({
            "code": entry["code"], "size_mm": float(found.group(2)), "raw_text": raw,
            "meaning": leg_meaning(entry), "ref_ids": m["ref_ids"],
        })
    return legs, conflicts


def vlm_texts(vlm_result: dict | None) -> set[tuple[str, float]] | None:
    """사진을 본 VLM이 읽은 글자 속 '코드 + 숫자' 표기 {(코드, 값)} — 한 줄에 여러 표기가 있어도(F5.5 V6) 하나씩.
    사진을 안 봤으면 None"""
    if not vlm_result or not vlm_result.get("image_attached"):
        return None
    return {(code, float(value)) for x in vlm_result["reading"]["texts"]
            for code, value in VLM_CODE_VALUE.findall(normalize(x["text"]))}


def ocr_only(reading: dict) -> bool:
    """1단계가 찾은 t* (작업자가 고치거나 확인한 것, VLM만 읽은 v*는 아님). VLM 읽기로 바꾼 t*도 넣음 —
    VLM 값이 사전에 안 맞으면 1단계 값이 후보로 다시 대조돼 각장이 될 수 있어서 ('Angle' ← 1단계 'F118.0')"""
    return reading["ref_id"][0] == "t" and not reading["corrected"]


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
