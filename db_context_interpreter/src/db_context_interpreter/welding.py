"""a. 용접 기준 DB: 표준 용접 기준표 대조"""
import re

from db_context_interpreter.ocr_text import ocr_variants
from db_context_interpreter.readings import corrections_by_target, normalize

# 사전 항목의 뜻에 적힌 AWS 자세 (예: V "2F 용접장 각장", PB "수평수직필릿 자세 (…, AWS 2F)")
POSITION = re.compile(r"(?<![0-9A-Za-z])([1-4][FG])(?![0-9A-Za-z])")
# 자세 표기 없이 같은 판 두께에 자세만 다른 기준 행이 여럿일 때 고르는 순서 — 2F(수평 필렛)가 선체 보강재 용접의 대표 자세
# (선박용접 용어사전 STD-0214)
POSITION_PREFERENCE = ("2F", "1F", "3F", "4F", "1G", "2G", "3G", "4G")
# 판 두께 표기: t=10, T10, t:12mm, 10t, 10.5T
THICKNESS = re.compile(r"^(?:T[=:]?([0-9]+(?:\.[0-9]+)?)(?:MM)?|([0-9]+(?:\.[0-9]+)?)(?:MM)?T)$")


def parse_thickness(value: str) -> float | None:
    return read_thickness(value)[0]


def read_thickness(value: str) -> tuple[float | None, str | None]:
    """(판 두께 mm, 그렇게 읽은 표기). 그대로 안 읽히면 OCR이 헷갈린 글자를 고쳐 봄 (t=1O → T=10)"""
    for candidate in [normalize(value), *ocr_variants(value)]:
        if m := THICKNESS.match(candidate):
            return float(m.group(1) or m.group(2)), candidate
    return None, None


def find_welding_condition(
    matches: list[dict], readings: list[dict], context_input: dict, legs: list[dict] | None = None,
) -> tuple[dict | None, list[dict]]:
    """사전 항목의 welding_joint_type + 판 두께 표기(예: t=10) 또는 수기 각장(예: F5.5)으로 context_input["welding_standards"]의
    행을 찾아 WeldingCondition을 만듦 (standard_matched, source="standard_db", ref_ids = 근거 표기) → (WeldingCondition | None, Conflict 목록).
    판 두께가 있으면 판 두께로, 없으면(PAC 손글씨처럼 각장만 있는 사진) 첫 번째 각장으로 기준 행을 고름.
    작업자가 welding_condition을 고쳤으면 그 값. 판별 못 하면 None"""
    correction = corrections_by_target(context_input).get("welding_condition")
    if correction:
        return dict(correction["value"]), []

    legs = legs or []
    conflicts = []
    joint_types = joint_type_marks(matches, context_input["symbols"])
    thicknesses = [(t, r) for r in readings if r["kind"] == "text" and (t := parse_thickness(r["value"])) is not None]
    if len(joint_types) > 1:
        detail = ", ".join(f"{jt}({', '.join(m['raw'] for m in ms)})" for jt, ms in joint_types.items())
        conflicts.append(standard_conflict(f"이음 형태 표기가 서로 다름: {detail}", "error",
                                           [ref for ms in joint_types.values() for m in ms for ref in m["ref_ids"]]))
    if len({t for t, _ in thicknesses}) > 1:
        detail = ", ".join(f"'{r['value']}'" for _, r in thicknesses)
        conflicts.append(standard_conflict(f"판 두께 표기가 여러 개임: {detail}", "warning", [r["ref_id"] for _, r in thicknesses]))
    if not joint_types:
        return None, conflicts

    joint_type, joint_marks = max(joint_types.items(), key=lambda kv: max(m["score"] for m in kv[1]))
    thickness, thickness_reading = max(thicknesses, key=lambda tr: tr[1]["prob"]) if thicknesses else (None, None)
    refs = [ref for m in joint_marks for ref in m["ref_ids"]] + ([thickness_reading["ref_id"]] if thickness_reading else [])
    rows = [s for s in context_input["welding_standards"] if s["joint_type"] == joint_type]
    if not rows:
        conflicts.append(standard_conflict(f"표준 용접 기준표에 이음 형태 {joint_type}가 없음", "error", refs))
        return None, conflicts

    positions, position_refs = position_marks(matches, context_input["symbols"])
    if positions:
        refs += position_refs
        rows = [r for r in rows if r["position"] in positions]
        if not rows:
            have = ", ".join(sorted({s["position"] for s in context_input["welding_standards"] if s["joint_type"] == joint_type}))
            conflicts.append(standard_conflict(
                f"표기된 자세({', '.join(sorted(positions))})의 {joint_type} 기준이 표준 용접 기준표에 없음 (있는 자세: {have})",
                "error", refs))
            return None, conflicts
    by_thickness = [r for r in rows if r["thickness_min_mm"] is not None]
    if thickness is not None and (by_thickness or not legs):
        if not by_thickness:
            conflicts.append(standard_conflict(f"판 두께로 고를 수 있는 {joint_type} 표준 용접 기준이 없음", "error", refs))
            return None, conflicts
        inside = [r for r in by_thickness if r["thickness_min_mm"] <= thickness <= r["thickness_max_mm"]]
        if not inside:
            have = ", ".join(f"{t:g}" for t in sorted({r["thickness_min_mm"] for r in by_thickness}))
            conflicts.append(standard_conflict(
                f"판 두께 {thickness:g}mm에 맞는 {joint_type} 표준 용접 기준이 없음 (기준표 판 두께: {have}mm)", "error", refs))
            return None, conflicts
        row = standard_row(inside, thickness)
        assumed = sorted({r["position"] for r in inside})
        if len(assumed) > 1:  # 자세 표기가 없어 자세를 정할 수 없음 → 대표 자세로 고르고 작업자 확인
            row = min(inside, key=lambda r: position_rank(r["position"]))
            conflicts.append(standard_conflict(
                f"자세 표기가 없어 {row['position']} 기준을 씀 (판 두께 {thickness:g}mm {joint_type} 기준 자세: {', '.join(assumed)})",
                "warning", refs))
        return condition(row, joint_type, thickness, None, refs, True), conflicts
    if legs:
        return by_leg_length(rows, legs, joint_type, thickness, refs, conflicts, context_input["symbols"])
    if len(rows) > 1:  # 판 두께·각장 없이는 기준 행을 고를 수 없음 → 작업자 확인(missing_required)
        return None, conflicts
    return condition(rows[0], joint_type, None, None, refs, True), conflicts


def by_leg_length(rows: list[dict], legs: list[dict], joint_type: str, thickness: float | None, refs: list[str],
                  conflicts: list[dict], entries: list[dict]) -> tuple[dict | None, list[dict]]:
    """첫 번째 각장(읽는 순서)의 자세(사전 뜻: F → 3F, V → 2F)와 크기로 기준 행을 고름.
    기준표는 각장별 값이라 사이 크기(5.5mm)는 가장 가까운 각장 행을 쓰고 작업자 확인 (standard_matched = false)"""
    primary = legs[0]
    entry = next((e for e in entries if e["code"] == primary["code"]), None)
    leg_positions = set(POSITION.findall(entry["meaning"])) if entry else set()
    refs = refs + primary["ref_ids"]
    size = primary["size_mm"]
    candidates = [r for r in rows if r.get("leg_min_mm") is not None and (not leg_positions or r["position"] in leg_positions)]
    where = f"{joint_type} {'·'.join(sorted(leg_positions))}".strip()
    if not candidates:
        conflicts.append(standard_conflict(
            f"각장 '{primary['raw_text']}'({size:g}mm)로 고를 수 있는 {where} 표준 용접 기준이 없음", "error", refs))
        return None, conflicts
    exact = [r for r in candidates if r["leg_min_mm"] <= size <= r["leg_max_mm"]]
    if exact:
        row, matched = min(exact, key=lambda r: position_rank(r["position"])), True
    else:
        row = min(candidates, key=lambda r: (leg_distance(r, size), -r["leg_min_mm"], position_rank(r["position"])))
        have = ", ".join(f"{v:g}" for v in sorted({r["leg_min_mm"] for r in candidates}))
        conflicts.append(standard_conflict(
            f"각장 {size:g}mm 기준이 없어 가장 가까운 각장 {leg_label(row)}mm {row['position']} 기준을 씀 "
            f"(기준표 {where} 각장: {have}mm)", "warning", refs))
        matched = False
    others = [leg for leg in legs[1:] if (leg["code"], leg["size_mm"]) != (primary["code"], size)]
    if others:
        conflicts.append(standard_conflict(
            f"각장 표기가 여러 개라 첫 번째 '{primary['raw_text']}' 기준으로 용접 조건을 고름 — "
            f"{', '.join(repr(leg['raw_text']) for leg in others)}의 용접 조건은 따로 확인",
            "info", [ref for leg in others for ref in leg["ref_ids"]]))
    return condition(row, joint_type, thickness, size, refs, matched), conflicts


def leg_distance(row: dict, size: float) -> float:
    return max(row["leg_min_mm"] - size, 0, size - row["leg_max_mm"])


def leg_label(row: dict) -> str:
    low, high = row["leg_min_mm"], row["leg_max_mm"]
    return f"{low:g}" if low == high else f"{low:g}~{high:g}"


def condition(row: dict, joint_type: str, thickness: float | None, leg: float | None, refs: list[str], matched: bool) -> dict:
    result = {
        "joint_type": joint_type,
        "thickness_mm": thickness,
        **{k: row[k] for k in ("process", "position", "current_a", "voltage_v", "speed_cm_min")},
        "standard_matched": matched,
        "source": "standard_db",
        "ref_ids": list(dict.fromkeys(refs)),
    }
    if leg is not None:
        result["leg_length_mm"] = leg
    return result


def joint_type_marks(matches: list[dict], entries: list[dict]) -> dict[str, list[dict]]:
    """사전 대조 결과 중 이음 형태(welding_joint_type)가 있는 것 → {joint_type: [DictionaryMatch]} (처음 나온 순서)"""
    by_code = {e["code"]: e for e in entries}
    marks: dict[str, list[dict]] = {}
    for m in matches:
        joint_type = (by_code.get(m["code"]) or {}).get("welding_joint_type")
        if joint_type:
            marks.setdefault(joint_type, []).append(m)
    return marks


def position_marks(matches: list[dict], entries: list[dict]) -> tuple[set[str], list[str]]:
    """사전 대조 결과 중 뜻에 AWS 자세(1F~4G)가 적힌 항목 → ({자세}, 근거 ref_ids)"""
    by_code = {e["code"]: e for e in entries}
    positions, refs = set(), []
    for m in matches:
        found = POSITION.findall((by_code.get(m["code"]) or {}).get("meaning", ""))
        if found:
            positions |= set(found)
            refs += m["ref_ids"]
    return positions, refs


def position_rank(position: str) -> int:
    return POSITION_PREFERENCE.index(position) if position in POSITION_PREFERENCE else len(POSITION_PREFERENCE)


def standard_row(rows: list[dict], thickness: float) -> dict | None:
    """판 두께가 들어가는 기준 행. 경계값(예: 12mm가 6~12 · 12~20 모두)은 그 값에서 시작하는 행을 고름"""
    inside = [r for r in rows if r["thickness_min_mm"] is not None and r["thickness_min_mm"] <= thickness <= r["thickness_max_mm"]]
    return next((r for r in inside if thickness < r["thickness_max_mm"]), inside[-1] if inside else None)


def standard_conflict(message: str, severity: str, refs: list[str]) -> dict:
    return {"type": "standard_conflict", "severity": severity, "message": message, "ref_ids": list(dict.fromkeys(refs))}
