"""a. 용접 기준 DB: 표준 용접 기준표 대조"""
import re

from db_context_interpreter.readings import corrections_by_target, normalize

# 판 두께 표기: t=10, T10, t:12mm, 10t, 10.5T
THICKNESS = re.compile(r"^(?:T[=:]?([0-9]+(?:\.[0-9]+)?)(?:MM)?|([0-9]+(?:\.[0-9]+)?)(?:MM)?T)$")


def parse_thickness(value: str) -> float | None:
    m = THICKNESS.match(normalize(value))
    return float(m.group(1) or m.group(2)) if m else None


def find_welding_condition(matches: list[dict], readings: list[dict], context_input: dict) -> tuple[dict | None, list[dict]]:
    """사전 항목의 welding_joint_type + 판 두께 표기(예: t=10)로 context_input["welding_standards"]의 행을 찾아
    WeldingCondition을 만듦 (standard_matched, source="standard_db", ref_ids = 근거 표기) → (WeldingCondition | None, Conflict 목록).
    작업자가 welding_condition을 고쳤으면 그 값. 판별 못 하면 None"""
    correction = corrections_by_target(context_input).get("welding_condition")
    if correction:
        return dict(correction["value"]), []

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
    if thickness is None:
        if len(rows) > 1:  # 판 두께 없이는 기준 행을 고를 수 없음 → 작업자 확인(missing_required)
            return None, conflicts
        row = rows[0]
    else:
        row = standard_row(rows, thickness)
        if row is None:
            low, high = min(r["thickness_min_mm"] for r in rows), max(r["thickness_max_mm"] for r in rows)
            conflicts.append(standard_conflict(
                f"판 두께 {thickness:g}mm는 {joint_type} 표준 용접 기준({low:g}~{high:g}mm) 범위 밖", "error", refs))
            return None, conflicts
    return {
        "joint_type": joint_type,
        "thickness_mm": thickness,
        **{k: row[k] for k in ("process", "position", "current_a", "voltage_v", "speed_cm_min")},
        "standard_matched": True,
        "source": "standard_db",
        "ref_ids": list(dict.fromkeys(refs)),
    }, conflicts


def joint_type_marks(matches: list[dict], entries: list[dict]) -> dict[str, list[dict]]:
    """사전 대조 결과 중 이음 형태(welding_joint_type)가 있는 것 → {joint_type: [DictionaryMatch]} (처음 나온 순서)"""
    by_code = {e["code"]: e for e in entries}
    marks: dict[str, list[dict]] = {}
    for m in matches:
        joint_type = (by_code.get(m["code"]) or {}).get("welding_joint_type")
        if joint_type:
            marks.setdefault(joint_type, []).append(m)
    return marks


def standard_row(rows: list[dict], thickness: float) -> dict | None:
    """판 두께가 들어가는 기준 행. 경계값(예: 12mm가 6~12 · 12~20 모두)은 그 값에서 시작하는 행을 고름"""
    inside = [r for r in rows if r["thickness_min_mm"] <= thickness <= r["thickness_max_mm"]]
    return next((r for r in inside if thickness < r["thickness_max_mm"]), inside[-1] if inside else None)


def standard_conflict(message: str, severity: str, refs: list[str]) -> dict:
    return {"type": "standard_conflict", "severity": severity, "message": message, "ref_ids": list(dict.fromkeys(refs))}
