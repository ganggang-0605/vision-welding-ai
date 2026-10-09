"""스키마로는 못 거르는 Analysis 안의 단계 사이 규칙"""
from vw_shared.ids import is_ref, vlm_only
from vw_shared.job_fields import to_job_fields


def semantic_errors(analysis: dict) -> list[str]:
    """Analysis 안의 단계 사이 규칙 (ID 참조, 신뢰도 계산 규칙, 필수 값). 맞으면 빈 목록"""
    errors = []
    vision, context, confidence = analysis["vision"], analysis["context"], analysis.get("confidence")
    corrections = analysis.get("corrections", [])
    text_ids = [t["id"] for t in vision["texts"]]
    symbol_ids = [s["id"] for s in vision["symbols"]]
    known = set(text_ids) | set(symbol_ids)
    if len(known) != len(text_ids) + len(symbol_ids):
        errors.append("vision: 인식 결과 id가 중복됨")
    vlm_ids = [x["ref_id"] for x in vlm_only(context)]
    if len(set(vlm_ids)) != len(vlm_ids):
        errors.append("context.vlm.reading: v* id가 중복됨")
    known |= set(vlm_ids)

    for t in vision["texts"]:
        if "char_probs" in t and len(t["char_probs"]) != len(t["text"]):
            errors.append(f"vision {t['id']}: char_probs 개수({len(t['char_probs'])})가 글자 수({len(t['text'])})와 다름")
        if t.get("candidates") and t["candidates"][0]["text"] != t["text"]:
            errors.append(f"vision {t['id']}: candidates 첫 번째가 text와 다름")

    refs = [r for m in context["dictionary_matches"] for r in m["ref_ids"]]
    refs += context["part"]["ref_ids"]
    refs += (context["welding_condition"] or {}).get("ref_ids", [])
    refs += [r for leg in context.get("leg_lengths", []) for r in leg["ref_ids"]]
    refs += (context.get("cell") or {}).get("ref_ids", [])
    refs += [r for c in context["conflicts"] for r in c["ref_ids"]]
    if context["vlm"]:
        reading = context["vlm"]["reading"]
        refs += [x["ref_id"] for x in reading["texts"] if x["ref_id"][0] == "t"]
        refs += [x["ref_id"] for x in reading["symbols"] if x["ref_id"][0] == "s"]
        for x in reading["texts"] + reading["symbols"]:
            if x.get("used") and x["ref_id"][0] == "v":
                errors.append(f"context.vlm.reading {x['ref_id']}: used는 1단계 결과(t*·s*)를 대신한 읽기에만 씀")
    if context.get("vlm_error") and context["vlm"]:
        errors.append("context: vlm_error가 있으면 vlm은 null이어야 함")
    refs += [c["target"] for c in corrections if is_ref(c["target"])]
    if confidence:
        refs += [r for e in confidence["evidence"] for r in e.get("ref_ids", [])]
        refs += [n["target"] for n in confidence["needs_review"] if is_ref(n["target"])]
        expected = min(confidence["visual"], confidence["db_consistency"], confidence["vlm_reasoning"])
        if confidence["overall"] != expected:
            errors.append(f"confidence: overall({confidence['overall']})은 세 신뢰도의 최솟값({expected})이어야 함")
        fields = to_job_fields(analysis)
        missing = [k for k in ("assembly_path", "welding_condition") if fields[k] is None]
        if confidence["passed"] != (confidence["overall"] >= confidence["threshold"] and not missing):
            errors.append(f"confidence: passed는 overall ≥ threshold이고 필수 값이 모두 있을 때만 true (빠진 값: {missing})")
        targets = {n["target"] for n in confidence["needs_review"]}
        for key, target in (("assembly_path", "part"), ("welding_condition", "welding_condition")):
            if key in missing and target not in targets:
                errors.append(f"confidence: {key}가 없는데 needs_review에 '{target}' 항목이 없음")
        corrected = {c["target"] for c in corrections}
        for n in confidence["needs_review"]:
            if n["target"] in corrected:
                errors.append(f"confidence: 작업자가 이미 고친 '{n['target']}'가 needs_review에 남아 있음")

    for r in sorted(set(refs) - known):
        errors.append(f"'{r}'를 참조하지만 인식 결과(vision, vlm.reading의 v*)에 없음")
    if (analysis.get("revision", 1) > 1) != bool(corrections or context.get("user_context")):
        errors.append("revision 2 이상은 작업자 확인(corrections 또는 user_context)으로만 생김")
    return errors
