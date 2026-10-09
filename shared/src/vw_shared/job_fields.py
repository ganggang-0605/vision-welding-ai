"""Analysis → 팀원 Job(backend/app/schemas.py)의 해석 결과 필드"""
import re
from datetime import datetime

from vw_shared.ids import is_ref, vlm_only

# backend/app/schemas.py의 WeldingCondition · Confidence 필드 (backend/tests/test_pipeline.py가 같은지 점검)
WELDING_CONDITION_FIELDS = ("joint_type", "process", "position", "current_a", "voltage_v", "speed_cm_min")
CONFIDENCE_FIELDS = ("visual", "db_consistency", "vlm_reasoning", "overall")


def latest_analysis(analyses: list[dict]) -> dict:
    """작업 하나의 Analysis 여러 개(사진 여러 장 · revision 여러 개) 중 Job에 반영할 것 = 가장 최근 created_at"""
    return max(analyses, key=lambda a: datetime.fromisoformat(a["created_at"]))


def vlm_used(context: dict) -> dict[str, str]:
    """2단계가 1단계 읽기 대신 해석에 쓴 VLM 읽기 {t*·s*: 값} (vlm.reading의 used)"""
    if not context["vlm"]:
        return {}
    reading = context["vlm"]["reading"]
    return {x["ref_id"]: x.get("text") or x.get("label") for x in reading["texts"] + reading["symbols"] if x.get("used")}


# raw_text에 넣지 않는 기호 label — 셀 형태(scallop 등)·unknown 같은 이름은 표기 원문이 아님 (marking.symbols에는 남김)
WORD_LABEL = re.compile(r"^[A-Za-z_]{2,}$")


def reading_order(vision: dict, context: dict, corrected: dict[str, str]) -> list[str]:
    """글자·기호를 줄 단위로 묶어 왼→오른, 위→아래 순서로 (작업자가 고친 값 > 2단계가 쓴 VLM 읽기 > 1단계 읽기).
    위치를 모르는 v* 표기는 맨 뒤. 이름으로 된 기호 label(scallop, unknown …)은 뺌"""
    used = vlm_used(context)
    items = [(d["bbox"], d["id"], d.get("text") or d.get("label"), "label" in d) for d in vision["texts"] + vision["symbols"]]
    items += [(x["bbox"], x["ref_id"], x.get("text") or x.get("label"), "label" in x) for x in vlm_only(context) if "bbox" in x]
    no_bbox = [corrected.get(x["ref_id"], x.get("text") or x.get("label")) for x in vlm_only(context)
               if "bbox" not in x and not ("label" in x and WORD_LABEL.match(x["label"]))]
    items = [(bbox, corrected.get(ref, used.get(ref, value))) for bbox, ref, value, symbol in items
             if not (symbol and ref not in corrected and WORD_LABEL.match(used.get(ref, value)))]
    items.sort(key=lambda it: (it[0][1] + it[0][3]) / 2)
    lines: list[list] = []
    for bbox, value in items:
        center = (bbox[1] + bbox[3]) / 2
        if lines and abs(center - lines[-1][0]) <= (lines[-1][1] / 2):
            lines[-1][2].append((bbox[0], value))
        else:
            lines.append([center, bbox[3] - bbox[1], [(bbox[0], value)]])
    return [value for _, _, line in lines for _, value in sorted(line)] + no_bbox


def to_job_fields(analysis: dict) -> dict:
    """Analysis → Job의 status · assembly_path · marking · welding_condition · cell · leg_lengths · confidence · evidence · needs_review"""
    vision, context, confidence = analysis["vision"], analysis["context"], analysis["confidence"]
    corrections = {c["target"]: c["value"] for c in analysis.get("corrections", [])}
    meanings = {c["target"]: c["meaning"] for c in analysis.get("corrections", []) if "meaning" in c}
    texts = {c: v for c, v in corrections.items() if is_ref(c)}
    wc = corrections.get("welding_condition") or context["welding_condition"]
    vlm = context["vlm"]
    symbols = [s["id"] for s in vision["symbols"]] + [x["ref_id"] for x in vlm_only(context) if "label" in x]
    labels = {s["id"]: s["label"] for s in vision["symbols"]} | {x["ref_id"]: x["label"] for x in vlm_only(context) if "label" in x}
    labels |= {ref: value for ref, value in vlm_used(context).items() if ref in labels}
    cell = context.get("cell")
    return {
        "status": "awaiting_approval" if confidence and confidence["passed"] else "needs_review",
        "assembly_path": corrections.get("part") or context["part"]["assembly_path"],
        "marking": {
            "raw_text": " ".join(reading_order(vision, context, texts)),
            "symbols": [texts.get(i, labels[i]) for i in symbols],
            "interpretation": corrections.get("interpretation") or (vlm["interpretation"] if vlm else ", ".join(
                m for m in (meanings.get(d["ref_ids"][0], d["meaning"]) for d in context["dictionary_matches"]) if m)),
        },
        "welding_condition": {k: wc[k] for k in WELDING_CONDITION_FIELDS} if wc else None,
        "cell": {"left": cell["left"], "right": cell["right"]} if cell else None,
        "leg_lengths": [{k: leg[k] for k in ("code", "size_mm", "raw_text", "meaning")} for leg in context.get("leg_lengths", [])],
        "confidence": {k: confidence[k] for k in CONFIDENCE_FIELDS} if confidence else None,
        "evidence": [e["message"] for e in confidence["evidence"]] if confidence else [],
        "needs_review": [n["message"] for n in confidence["needs_review"]] if confidence else [],
    }
