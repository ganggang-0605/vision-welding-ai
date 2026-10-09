"""a. 시각 인식 신뢰도: OCR/기호 인식 확률, 전처리 보정 강도, OCR↔VLM 교차 검증 일치도"""


def visual_factors(vision: dict, context: dict, corrections: list[dict]) -> dict:
    confirmed = {c["target"] for c in corrections}
    probs = [d["prob"] for d in vision["texts"] + vision["symbols"] if d["id"] not in confirmed]
    return {
        "recognition_prob": min(probs) if probs else None,  # 작업자가 확인하지 않은 것 중 가장 낮은 확률
        "correction_strength": vision["preprocess"]["correction_strength"],
        "ocr_vlm_agreement": ocr_vlm_agreement(vision, context),
    }


def ocr_vlm_agreement(vision: dict, context: dict) -> float | None:
    """1단계와 VLM이 같게 읽은 표기 비율. 한쪽만 읽은 표기(VLM만 읽은 v*, VLM이 놓친 1단계 결과)는 불일치. VLM이 없으면 None"""
    if not context["vlm"]:
        return None
    read = {d["id"]: d.get("text") or d.get("label") for d in vision["texts"] + vision["symbols"]}
    reading = context["vlm"]["reading"]["texts"] + context["vlm"]["reading"]["symbols"]
    agreed = sum(1 for x in reading if read.get(x["ref_id"]) == (x.get("text") or x.get("label")))
    total = len(reading) + len(read.keys() - {x["ref_id"] for x in reading})
    return round(agreed / total, 2) if total else None


def visual_score(factors: dict) -> float:
    """0~100. TODO: 인식 확률 + 보정 강도 감점 + 교차 검증 일치 가산 (가중치는 조정 예정)"""
    return 0.0
