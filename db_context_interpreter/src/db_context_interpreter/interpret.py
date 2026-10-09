"""[2단계] 진입점: VLM 해석 → 부재·조립 경로 → 사전 대조 → 용접 조건 → DB 불일치"""
from db_context_interpreter.assembly import find_part, tree_hits
from db_context_interpreter.dictionary import dictionary_conflicts, match_dictionary
from db_context_interpreter.readings import collect_readings, normalize
from db_context_interpreter.vlm import VlmOutput, interpret_with_vlm
from db_context_interpreter.welding import find_welding_condition


def interpret(vision_result: dict, context_input: dict, image=None, previous_vlm: dict | None = None) -> dict:
    """VisionResult + ContextInput → ContextResult. 작업자 확인(재해석·직접 해석) 때도 이 함수부터 다시 돌림.
    image: VLM에 보여 줄 원본 사진 (선택, vlm.interpret_with_vlm 참고)
    previous_vlm: 이전 revision의 ContextResult.vlm (작업자 확인 때). VLM이 꺼졌거나 실패했는데
    작업자가 VLM만 읽은 표기(v*)를 고쳤으면 이 결과를 그대로 이어 씀 — 고친 v*가 가리킬 대상이 사라지지 않게"""
    vlm = interpret_with_vlm(vision_result, context_input, image)
    if vlm is None and previous_vlm and any(c["target"][0] == "v" for c in context_input["corrections"]):
        vlm = VlmOutput(result=previous_vlm, meanings={})
    vlm_result = vlm.result if vlm else None
    vlm_prob = vlm.prob if vlm else 0.0
    readings = collect_readings(vision_result, context_input, vlm_result["reading"] if vlm_result else None, vlm_prob)

    part, part_conflicts = find_part(readings, context_input)
    # 부재 번호로 쓴 표기는 사전 대조에서 뺌 (고른 부재와 다른 갈래의 부재 표기도)
    part_refs = set(part["ref_ids"]) | {h["ref_id"] for h in tree_hits(readings, context_input["assembly_tree"])}
    matches = match_dictionary(readings, context_input, vlm.meanings if vlm else {}, vlm_prob, part_refs)
    welding_condition, welding_conflicts = find_welding_condition(matches, readings, context_input)
    return {
        "user_context": context_input["user_context"],
        # 연결된 과거 작업은 VLM 프롬프트의 맥락으로만 씀
        "related_job_ids": [j["job_id"] for j in context_input["related_jobs"]] if vlm else [],
        "dictionary_matches": matches,
        "part": part,
        "welding_condition": welding_condition,
        "conflicts": part_conflicts + dictionary_conflicts(matches, readings, context_input)
                     + welding_conflicts + find_conflicts(vision_result, readings, vlm_result),
        "vlm": vlm_result,
    }


def find_conflicts(vision_result: dict, readings: list[dict], vlm: dict | None) -> list[dict]:
    """ocr_vlm_mismatch: 1단계와 VLM이 다르게 읽은 표기 · 1단계가 놓치고 VLM만 읽은 표기 (작업자가 확인한 것은 뺌).
    나머지 Conflict(dictionary_unmatched · part_not_in_tree · standard_conflict · ambiguous_reading)는 각 DB 모듈이 만듦"""
    if not vlm:
        return []
    current = {r["ref_id"]: r for r in readings}
    conflicts = []
    for kind, field in (("texts", "text"), ("symbols", "label")):
        for x in vlm["reading"][kind]:
            r = current.get(x["ref_id"])
            if r is None or r["corrected"]:
                continue
            if x["ref_id"][0] == "v":
                conflicts.append({
                    "type": "ocr_vlm_mismatch", "severity": "warning",
                    "message": f"1단계 인식이 놓친 표기 '{x[field]}'를 VLM이 읽음", "ref_ids": [x["ref_id"]],
                })
            elif normalize(x[field]) != normalize(r["value"]):
                conflicts.append({
                    "type": "ocr_vlm_mismatch", "severity": "warning",
                    "message": f"1단계는 '{r['value']}', VLM은 '{x[field]}'로 읽음", "ref_ids": [x["ref_id"]],
                })
    read_by_vlm = {x["ref_id"] for kind in ("texts", "symbols") for x in vlm["reading"][kind]}
    for d in vision_result["texts"] + vision_result["symbols"]:
        if d["id"] not in read_by_vlm and not current[d["id"]]["corrected"]:
            conflicts.append({
                "type": "ocr_vlm_mismatch", "severity": "info",
                "message": f"1단계가 읽은 '{d.get('text') or d.get('label')}'를 VLM은 읽지 못함", "ref_ids": [d["id"]],
            })
    return conflicts
