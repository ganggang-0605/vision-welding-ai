"""a. 시각 인식 신뢰도: OCR/기호 인식 확률, 전처리 보정 강도, OCR↔VLM 교차 검증 일치도"""

STRONG_CORRECTION = 0.5  # 전처리 보정 강도가 이보다 세면 원본에서 멀어진 만큼 깎음 (최대 20%)
MAX_CORRECTION_PENALTY = 0.2


def visual_factors(vision: dict, context: dict, corrections: list[dict]) -> dict:
    confirmed = {c["target"] for c in corrections}
    found = vision["texts"] + vision["symbols"]
    probs = [d["prob"] for d in found if d["id"] not in confirmed]
    return {
        # 작업자가 확인하지 않은 것 중 가장 낮은 확률. 모두 확인했으면 1, 1단계가 아무것도 못 읽었으면 None
        "recognition_prob": min(probs) if probs else (1.0 if found else None),
        "correction_strength": vision["preprocess"]["correction_strength"],
        "ocr_vlm_agreement": ocr_vlm_agreement(vision, context, confirmed),
    }


def ocr_vlm_agreement(vision: dict, context: dict, confirmed: set[str] = frozenset()) -> float | None:
    """1단계와 VLM이 같게 읽은 표기 비율. 한쪽만 읽은 표기(VLM만 읽은 v*, VLM이 놓친 1단계 결과)는 불일치,
    작업자가 확인한 표기는 일치. VLM이 없으면 None"""
    if not context["vlm"]:
        return None
    read = {d["id"]: d.get("text") or d.get("label") for d in vision["texts"] + vision["symbols"]}
    reading = context["vlm"]["reading"]["texts"] + context["vlm"]["reading"]["symbols"]
    agreed = sum(1 for x in reading
                 if x["ref_id"] in confirmed or read.get(x["ref_id"]) == (x.get("text") or x.get("label")))
    missed = read.keys() - {x["ref_id"] for x in reading}
    agreed += len(missed & confirmed)
    total = len(reading) + len(missed)
    return round(agreed / total, 2) if total else None


def visual_score(factors: dict) -> float:
    """0~100 = 인식 확률과 OCR↔VLM 일치도 중 낮은 것 × 보정 강도 감점. 둘 다 없으면(읽은 표기가 없음) 0"""
    values = [v for v in (factors["recognition_prob"], factors["ocr_vlm_agreement"]) if v is not None]
    if not values:
        return 0.0
    strength = factors["correction_strength"] or 0.0
    penalty = MAX_CORRECTION_PENALTY * max(0.0, strength - STRONG_CORRECTION) / (1 - STRONG_CORRECTION)
    return round(100 * min(values) * (1 - penalty))
