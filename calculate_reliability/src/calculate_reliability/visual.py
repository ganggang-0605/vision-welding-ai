"""a. 시각 인식 신뢰도: OCR/기호 인식 확률, 전처리 보정 강도, OCR↔VLM 교차 검증 일치도"""
import re
import unicodedata

STRONG_CORRECTION = 0.5  # 전처리 보정 강도가 이보다 세면 원본에서 멀어진 만큼 깎음 (최대 20%)
MAX_CORRECTION_PENALTY = 0.2
# 1단계가 아무것도 못 읽고 사진을 본 VLM만 읽었을 때 (손글씨 등): 교차 검증할 OCR 읽기가 없어 VLM 다중 추론 일관성으로 대신함
VLM_ONLY_CAP = 0.9     # 일관성이 1이어도 90 (OCR 확인 없이 VLM 한 모델만 본 것)
VLM_ONLY_SINGLE = 0.6  # 추론 1번이라 일관성도 잴 수 없음 → 60 (작업자 확인)


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


ARROWS = re.compile(r"[\u2190-\u21ff\u2794\u279c\u27a1\u25b6\u25ba\u25c0\u25c4]")  # → ← ⇒ ➔ ▶ ◀ …


def same_reading(a: str | None, b: str | None) -> bool:
    """같은 표기로 읽었는지 — 공백·대소문자·전각·대시 모양과 글자에 붙은 화살표는 무시.
    1단계는 화살표를 글자와 한 줄로 읽고(→F7.5) VLM은 화살표를 기호로 따로 읽어서(F7.5 + →) 그대로 비교하면 불일치가 됨"""
    def key(value: str | None) -> str:
        value = ARROWS.sub("", unicodedata.normalize("NFKC", value or "").upper())
        return re.sub(r"\s+", "", re.sub(r"[‐‑‒–—―−_]", "-", value))
    return key(a) == key(b)


def ocr_vlm_agreement(vision: dict, context: dict, confirmed: set[str] = frozenset()) -> float | None:
    """1단계가 읽은 표기 중 VLM도 같게 읽은 비율 (VLM이 놓친 1단계 결과는 불일치, 작업자가 확인한 표기는 일치).
    VLM만 읽은 v*는 비교할 1단계 읽기가 없어 빼고, 시각 점수에서 따로 봄(vlm_only_reading).
    VLM이 없거나 1단계가 아무것도 못 읽었으면 None"""
    read = {d["id"]: d.get("text") or d.get("label") for d in vision["texts"] + vision["symbols"]}
    if not context["vlm"] or not read:
        return None
    reading = context["vlm"]["reading"]
    by_ref = {x["ref_id"]: x.get("text") or x.get("label") for x in reading["texts"] + reading["symbols"]}
    agreed = sum(1 for ref, value in read.items() if ref in confirmed or (ref in by_ref and same_reading(by_ref[ref], value)))
    return round(agreed / len(read), 2)


def vlm_only_reading(vision: dict, context: dict) -> bool:
    """1단계가 아무것도 못 읽었는데 사진을 본 VLM이 표기를 읽음 (손글씨처럼 OCR이 못 읽는 사진)"""
    vlm = context["vlm"]
    if not vlm or vision["texts"] or vision["symbols"] or vlm.get("image_attached") is False:
        return False
    return bool(vlm["reading"]["texts"] or vlm["reading"]["symbols"])


def visual_score(factors: dict, vlm_factors: dict | None = None, vlm_only: bool = False) -> float:
    """0~100 = 인식 확률과 OCR↔VLM 일치도 중 낮은 것 × 보정 강도 감점.
    둘 다 없을 때: 사진을 본 VLM만 읽었으면(vlm_only) VLM 다중 추론 일관성 × 0.9 (추론 1번이면 60), 아무도 못 읽었으면 0"""
    values = [v for v in (factors["recognition_prob"], factors["ocr_vlm_agreement"]) if v is not None]
    if not values and vlm_only:
        consistency = (vlm_factors or {}).get("consistency")
        values = [VLM_ONLY_CAP * consistency if consistency is not None else VLM_ONLY_SINGLE]
    if not values:
        return 0.0
    strength = factors["correction_strength"] or 0.0
    penalty = MAX_CORRECTION_PENALTY * max(0.0, strength - STRONG_CORRECTION) / (1 - STRONG_CORRECTION)
    return round(100 * min(values) * (1 - penalty))
