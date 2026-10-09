"""작업자 확인 항목 (ConfidenceReport.needs_review)과 판단 근거 (ConfidenceReport.evidence)"""
from vw_shared import is_ref

REQUIRED = (  # 로봇 JSON 필수 값 → 없으면 통과(passed)시킬 수 없음
    ("part", "부재·조립 경로를 찾지 못해 확인이 필요합니다"),
    ("welding_condition", "용접 조건을 판별하지 못해 확인이 필요합니다"),
)
STYLE = {"handwritten": "손글씨", "stamped": "각인", "stencil": "스텐실", "printed": "인쇄"}
# 2단계 Conflict.type → 확인 대상 (ref_ids가 없거나 대상이 더 분명한 것)
CONFLICT_TARGET = {"part_not_in_tree": "part", "standard_conflict": "welding_condition"}
SEVERITY_ORDER = {"error": 0, "warning": 1}


def missing_required(context: dict, corrections: list[dict]) -> list[str]:
    """작업자 수정까지 반영해도 비어 있는 필수 값의 확인 대상 (part, welding_condition)"""
    corrected = {c["target"] for c in corrections}
    present = {"part": context["part"]["assembly_path"], "welding_condition": context["welding_condition"]}
    return [target for target, _ in REQUIRED if target not in corrected and not present[target]]


def used_readings(context: dict) -> dict[str, str]:
    """2단계가 1단계 대신 해석에 쓴 VLM 읽기 {t*·s*: 값}"""
    if not context["vlm"]:
        return {}
    reading = context["vlm"]["reading"]
    return {x["ref_id"]: x.get("text") or x.get("label") for x in reading["texts"] + reading["symbols"] if x.get("used")}


def review_items(vision: dict, context: dict, corrections: list[dict], factors: dict, missing: list[str],
                 threshold: float, passed: bool) -> list[dict]:
    """필수 값 없음 → 2단계 error · warning 불일치 → 확률 낮은 표기 → VLM 추론 불일치 · 실패 순서, 대상마다 하나.
    작업자가 이미 고치거나 확인한 대상은 넣지 않음. 통과하지 못했는데 항목이 없으면 info 불일치 중 해석을 짐작한 것을 넣음"""
    corrected = {c["target"] for c in corrections}
    items: list[dict] = []
    seen: set[str] = set()

    def add(target: str, reason: str, message: str, candidates: list[str] | None = None) -> None:
        if target in corrected or target in seen:
            return
        seen.add(target)
        item = {"target": target, "reason": reason, "message": message}
        if candidates:
            item["candidates"] = candidates
        items.append(item)

    for target, message in REQUIRED:
        if target in missing:
            add(target, "missing_required", message)
    conflicts = sorted((c for c in context["conflicts"] if c["severity"] in SEVERITY_ORDER),
                       key=lambda c: SEVERITY_ORDER[c["severity"]])
    for c in conflicts:
        add(conflict_target(c), c["type"], c["message"])

    used = used_readings(context)
    low = threshold / 100
    for d in sorted(vision["texts"] + vision["symbols"], key=lambda d: d["prob"]):
        if d["prob"] >= low:
            continue
        value = d.get("text") or d.get("label")
        kind = STYLE.get(d.get("style"), "기호" if "label" in d else "")
        if d["id"] in used:
            message = f"{kind} 표기 '{used[d['id']]}' 확인 필요 (1단계는 '{value}' {d['prob']:.0%}, VLM 읽기를 씀)".strip()
            candidates = [used[d["id"]], value]
        else:
            message = f"{kind} 표기 '{value}' 확인 필요".strip()
            candidates = [c.get("text") or c.get("label") for c in d.get("candidates", [])] or [value]
        add(d["id"], "low_visual_confidence", message, list(dict.fromkeys(candidates)))

    vlm = context["vlm"]
    if context.get("vlm_error"):
        add("interpretation", "vlm_failed", f"VLM 해석이 실패해 사전 대조만으로 해석했습니다 ({context['vlm_error']})")
    elif vlm and vlm["consistency"] is not None and vlm["consistency"] < 1:
        add("interpretation", "vlm_inconsistent",
            f"VLM {vlm['runs']}번 추론 중 읽기가 일치한 비율이 {vlm['consistency']:.0%}라 해석 확인이 필요합니다")

    if not passed and not items:
        for c in context["conflicts"]:
            if c["type"] in ("dictionary_unmatched", "ocr_vlm_mismatch"):
                add(conflict_target(c), c["type"], c["message"])
    return items


def conflict_target(conflict: dict) -> str:
    if conflict["type"] in CONFLICT_TARGET:
        return CONFLICT_TARGET[conflict["type"]]
    refs = [r for r in conflict["ref_ids"] if is_ref(r)]
    return refs[0] if refs else "interpretation"


def evidence(vision: dict, context: dict, corrections: list[dict], factors: dict) -> list[dict]:
    """세 신뢰도마다 판단 근거 (layer, message, ref_ids)"""
    items: list[dict] = []

    def add(layer: str, message: str, refs: list[str] | None = None) -> None:
        item = {"layer": layer, "message": message}
        if refs:
            item["ref_ids"] = refs
        items.append(item)

    # a. 시각 인식
    confirmed = {c["target"]: c for c in corrections if is_ref(c["target"])}
    for target, c in confirmed.items():
        add("visual", f"작업자가 '{target}'를 '{c['value']}'로 확인", [target])
    found = [d for d in vision["texts"] + vision["symbols"] if d["id"] not in confirmed]
    visual = factors["visual"]
    if found:
        lowest = min(found, key=lambda d: d["prob"])
        add("visual", f"인식 확률이 가장 낮은 표기 '{lowest.get('text') or lowest.get('label')}' {lowest['prob']:.0%}", [lowest["id"]])
    elif not vision["texts"] and not vision["symbols"]:
        add("visual", "1단계 인식이 표기를 찾지 못함")
    if visual["ocr_vlm_agreement"] is not None and context["vlm"]:
        reading = context["vlm"]["reading"]
        add("visual", f"OCR과 VLM 읽기 일치도 {visual['ocr_vlm_agreement']:.0%} (VLM이 읽은 표기 {len(reading['texts']) + len(reading['symbols'])}개)")
    if (visual["correction_strength"] or 0) > 0.5:
        add("visual", f"전처리 보정이 강함 ({visual['correction_strength']:.0%}) — 원본과 달라졌을 수 있음")

    # b. DB 정합성
    part = context["part"]
    if any(c["target"] == "part" for c in corrections):
        add("db_consistency", f"작업자가 조립 경로를 {part['assembly_path']}로 정함")
    elif part["assembly_path"] and part["found_in_tree"] and part["ref_ids"]:
        add("db_consistency", f"부재 {part['node_id']}이 조립 트리 {part['assembly_path']}에 존재", part["ref_ids"])
    elif part["assembly_path"] and part["found_in_tree"]:
        add("db_consistency", f"사진에 부재 표기가 없어 작업에 적은 조립 경로 {part['assembly_path']}를 씀")
    elif part["node_id"]:
        add("db_consistency", f"부재 표기 {part['node_id']}이 조립 트리에 없음", part["ref_ids"] or None)
    rate = factors["db_consistency"]["dictionary_match_rate"]
    if rate is not None:
        add("db_consistency", f"사전·표기 규칙에 맞는 표기 {rate:.0%} ({len(context['dictionary_matches'])}개 중)")
    wc = context["welding_condition"]
    conflicts = factors["db_consistency"]["standard_conflicts"]
    if wc and wc.get("source") == "manual":
        add("db_consistency", "작업자가 용접 조건을 직접 입력")
    elif wc:
        basis = " · ".join(b for b in (
            f"판 두께 {wc['thickness_mm']:g}mm" if wc.get("thickness_mm") is not None else "",
            f"각장 {wc['leg_length_mm']:g}mm" if wc.get("leg_length_mm") is not None else "",
        ) if b)
        state = "표준 용접 기준과 충돌 없음" if wc["standard_matched"] and not conflicts else f"표준 용접 기준과 충돌 {conflicts}건"
        add("db_consistency", f"{wc['joint_type']} {wc['position']}{' · ' + basis if basis else ''}가 {state}", wc.get("ref_ids") or None)

    # c. VLM 추론
    vlm = context["vlm"]
    if context.get("vlm_error"):
        add("vlm_reasoning", f"VLM 호출 실패: {context['vlm_error']}")
    elif not vlm:
        add("vlm_reasoning", "VLM을 쓰지 않아 이 신뢰도는 판단에서 뺌")
    elif vlm["consistency"] == 1:
        add("vlm_reasoning", f"{vlm['runs']}회 추론 해석 모두 일치")
    elif vlm["consistency"] is not None:
        add("vlm_reasoning", f"{vlm['runs']}회 추론 중 일치 {vlm['consistency']:.0%}")
    elif vlm["token_prob"] is None:
        add("vlm_reasoning", "추론 1회라 일관성을 잴 수 없음 (VLM_RUNS를 2 이상으로 하면 잼)")
    if vlm and vlm["token_prob"] is not None:
        add("vlm_reasoning", f"출력 토큰 확률 {vlm['token_prob']:.0%}")
    return items
