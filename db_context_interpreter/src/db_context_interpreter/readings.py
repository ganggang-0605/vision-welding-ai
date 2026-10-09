"""2단계가 해석할 읽기 목록: 1단계 글자·기호 + VLM만 읽은 v* — 작업자 수정(corrections)을 1단계 읽기보다 우선"""
import re
import unicodedata

CORRECTED_PROB = 1.0  # 작업자가 고치거나 확인한 읽기의 확률


def normalize(value: str) -> str:
    """대조용 정규화: 전각→반각, 대문자, 공백 제거, 여러 가지 대시를 '-'로"""
    value = unicodedata.normalize("NFKC", value).upper()
    value = re.sub(r"[‐‑‒–—―−_]", "-", value)
    return re.sub(r"\s+", "", value)


def corrections_by_target(context_input: dict) -> dict[str, dict]:
    return {c["target"]: c for c in context_input["corrections"]}


def collect_readings(vision_result: dict, context_input: dict, vlm_reading: dict | None, vlm_prob: float) -> list[dict]:
    """읽기 하나 = {ref_id, kind(text|symbol), value, prob, candidates[(값, 확률)], corrected, meaning}.
    1단계 글자 → 기호 → VLM만 읽은 v* 순서. meaning은 작업자가 직접 정한 의미 (없으면 None)"""
    fixed = corrections_by_target(context_input)
    readings = []

    def add(ref_id: str, kind: str, value: str, prob: float, candidates: list[tuple[str, float]]) -> None:
        correction = fixed.get(ref_id)
        if correction:
            value, prob, candidates = correction["value"], CORRECTED_PROB, []
        readings.append({
            "ref_id": ref_id, "kind": kind, "value": value, "prob": prob, "candidates": candidates,
            "corrected": correction is not None, "meaning": correction.get("meaning") if correction else None,
        })

    for t in vision_result["texts"]:
        add(t["id"], "text", t["text"], t["prob"], [(c["text"], c["prob"]) for c in t.get("candidates", [])[1:]])
    for s in vision_result["symbols"]:
        add(s["id"], "symbol", s["label"], s["prob"], [(c["label"], c["prob"]) for c in s.get("candidates", [])
                                                       if c["label"] != s["label"]])
    if vlm_reading:
        for x in vlm_reading["texts"]:
            if x["ref_id"][0] == "v":
                add(x["ref_id"], "text", x["text"], vlm_prob, [])
        for x in vlm_reading["symbols"]:
            if x["ref_id"][0] == "v":
                add(x["ref_id"], "symbol", x["label"], vlm_prob, [])
    return readings
