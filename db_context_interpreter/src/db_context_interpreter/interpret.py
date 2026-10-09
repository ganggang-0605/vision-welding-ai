"""[2단계] 진입점: VLM 해석 → 읽기 정리(VLM 읽기 반영 · 줄 나누기) → 부재·조립 경로 → 사전 대조 → 각장 · 셀 형태 → 용접 조건 → DB 불일치"""
import copy
from collections.abc import Callable

from db_context_interpreter.assembly import TreeIndex, find_part
from db_context_interpreter.dictionary import Dictionary, dictionary_conflicts, match_dictionary
from db_context_interpreter.legs import find_cell, find_leg_lengths
from db_context_interpreter.ocr_text import ocr_variants, segment
from db_context_interpreter.readings import collect_readings, normalize
from db_context_interpreter.vlm import VlmOutput, run_vlm
from db_context_interpreter.welding import find_welding_condition, parse_thickness

# 1단계 확률이 이보다 낮으면 사진을 본 VLM이 다르게 읽은 값을 씀 (PAC 손글씨: OCR '—4' 57% ↔ VLM 'F4.5')
OCR_TRUSTED = 0.9


def interpret(vision_result: dict, context_input: dict, image=None, previous_vlm: dict | None = None) -> dict:
    """VisionResult + ContextInput → ContextResult. 작업자 확인(재해석·직접 해석) 때도 이 함수부터 다시 돌림.
    image: VLM에 보여 줄 사진 (선택, vlm.run_vlm 참고)
    previous_vlm: 이전 revision의 ContextResult.vlm (작업자 확인 때). VLM이 꺼졌거나 실패했는데
    작업자가 VLM만 읽은 표기(v*)를 고쳤으면 이 결과를 그대로 이어 씀 — 고친 v*가 가리킬 대상이 사라지지 않게"""
    vlm, vlm_error = run_vlm(vision_result, context_input, image)
    if vlm is None and previous_vlm and any(c["target"][0] == "v" for c in context_input["corrections"]):
        vlm = VlmOutput(result=copy.deepcopy(previous_vlm), meanings={})
    vlm_result = vlm.result if vlm else None
    vlm_prob = vlm.prob if vlm else 0.0
    known = known_marking(context_input)
    prefer = prefer_vlm(known) if vlm_result and vlm_result.get("image_attached") else None
    readings = collect_readings(vision_result, context_input, vlm_result["reading"] if vlm_result else None, vlm_prob, prefer)
    if vlm_result:
        vlm_result = mark_used(vlm_result, {r["ref_id"] for r in readings if r["vlm_used"]})
    readings = segment(readings, known)  # OCR이 한 줄로 읽은 표기 나누기 (P-1 FW t=10)

    # 부재 번호로 쓴 읽기는 사전 대조에서 뺌 (고른 부재와 다른 갈래의 부재 표기도)
    part, part_conflicts, part_keys = find_part(readings, context_input)
    pairs = match_dictionary(readings, context_input, vlm.meanings if vlm else {}, vlm_prob, part_keys)
    matches = [m for _, m in pairs]
    leg_lengths, leg_conflicts = find_leg_lengths(pairs, context_input, vlm_result)
    cell, cell_conflicts = find_cell(pairs, context_input, vision_result, vlm_result)
    welding_condition, welding_conflicts = find_welding_condition(matches, readings, context_input, leg_lengths)
    result = {
        "user_context": context_input["user_context"],
        # 연결된 과거 작업은 VLM 프롬프트의 맥락으로만 씀
        "related_job_ids": [j["job_id"] for j in context_input["related_jobs"]] if vlm else [],
        "dictionary_matches": matches,
        "part": part,
        "welding_condition": welding_condition,
        "leg_lengths": leg_lengths,
        "cell": cell,
        "conflicts": part_conflicts + dictionary_conflicts(pairs, context_input) + leg_conflicts + cell_conflicts
                     + welding_conflicts + find_conflicts(vision_result, readings, vlm_result),
        "vlm": vlm_result,
    }
    if vlm_error and vlm_result is None:
        result["vlm_error"] = vlm_error
    return result


def known_marking(context_input: dict) -> Callable[[str], bool]:
    """사전 · 조립 트리 · 판 두께로 해석되는 표기인지 (OCR이 헷갈린 글자를 고친 읽기 포함) — 줄 나누기 기준"""
    dictionary, tree = Dictionary(context_input["symbols"]), TreeIndex(context_input["assembly_tree"])

    def known(value: str) -> bool:
        if parse_thickness(value) is not None:
            return True
        return any(dictionary.lookup(v) or dictionary.code_with_value(v) or tree.lookup(v)
                   for v in [value, *ocr_variants(value)])

    return known


def prefer_vlm(known: Callable[[str], bool]) -> Callable[[str, float, str], bool]:
    """사진을 본 VLM이 1단계와 다르게 읽었을 때 VLM 값을 쓸지: VLM 값만 사전·트리·판 두께 규칙에 맞거나,
    1단계 확률이 낮고(< OCR_TRUSTED) VLM 값이 1단계 값보다 못하지 않을 때 (VLM이 'unknown'이면 쓰지 않음)"""
    def prefer(ocr: str, prob: float, vlm: str) -> bool:
        if vlm == "unknown":
            return False
        if known(vlm) and not known(ocr):
            return True
        return prob < OCR_TRUSTED and (known(vlm) or not known(ocr))

    return prefer


def mark_used(vlm_result: dict, used: set[str]) -> dict:
    """vlm.reading에서 2단계가 1단계 대신 쓴 t*·s* 읽기에 used: true (이전 revision 값은 지우고 다시 붙임)"""
    result = copy.deepcopy(vlm_result)
    for kind in ("texts", "symbols"):
        for x in result["reading"][kind]:
            x.pop("used", None)
            if x["ref_id"] in used:
                x["used"] = True
    return result


def find_conflicts(vision_result: dict, readings: list[dict], vlm: dict | None) -> list[dict]:
    """ocr_vlm_mismatch: 1단계와 VLM이 다르게 읽은 표기 · 1단계가 놓치고 VLM만 읽은 표기 (작업자가 확인한 것은 뺌).
    VLM 읽기를 쓴 표기와 VLM만 읽은 표기는 info — 해석은 됐고 경고가 쌓이지 않게. 1단계가 아무것도 못 읽었으면 하나로 묶음.
    나머지 Conflict(dictionary_unmatched · part_not_in_tree · standard_conflict · ambiguous_reading)는 각 DB 모듈이 만듦"""
    if not vlm:
        return []
    current: dict[str, dict] = {}
    for r in readings:  # 1단계 ID마다 하나 (줄을 나눈 읽기는 line이 줄 전체)
        current.setdefault(r["ref_id"], r)
    conflicts, vlm_only = [], []
    for kind, field in (("texts", "text"), ("symbols", "label")):
        for x in vlm["reading"][kind]:
            r = current.get(x["ref_id"])
            if r is None or r["corrected"]:
                continue
            if x["ref_id"][0] == "v":
                vlm_only.append((x["ref_id"], x[field]))
            elif r["vlm_used"]:
                conflicts.append({
                    "type": "ocr_vlm_mismatch", "severity": "info",
                    "message": f"1단계는 '{r['ocr_value']}', VLM은 '{x[field]}'로 읽어 사진을 본 VLM 읽기를 씀", "ref_ids": [x["ref_id"]],
                })
            elif normalize(x[field]) != normalize(r["line"]):
                conflicts.append({
                    "type": "ocr_vlm_mismatch", "severity": "warning",
                    "message": f"1단계는 '{r['line']}', VLM은 '{x[field]}'로 읽음", "ref_ids": [x["ref_id"]],
                })
    if vlm_only and not vision_result["texts"] and not vision_result["symbols"]:
        conflicts.append({
            "type": "ocr_vlm_mismatch", "severity": "info",
            "message": f"1단계 인식이 표기를 하나도 찾지 못해 VLM이 읽은 {len(vlm_only)}개를 씀: "
                       + ", ".join(f"'{value}'" for _, value in vlm_only),
            "ref_ids": [ref for ref, _ in vlm_only],
        })
    else:
        conflicts += [{
            "type": "ocr_vlm_mismatch", "severity": "info",
            "message": f"1단계 인식이 놓친 표기 '{value}'를 VLM이 읽음", "ref_ids": [ref],
        } for ref, value in vlm_only]
    read_by_vlm = {x["ref_id"] for kind in ("texts", "symbols") for x in vlm["reading"][kind]}
    for d in vision_result["texts"] + vision_result["symbols"]:
        if d["id"] not in read_by_vlm and not current[d["id"]]["corrected"]:
            conflicts.append({
                "type": "ocr_vlm_mismatch", "severity": "info",
                "message": f"1단계가 읽은 '{d.get('text') or d.get('label')}'를 VLM은 읽지 못함", "ref_ids": [d["id"]],
            })
    return conflicts
