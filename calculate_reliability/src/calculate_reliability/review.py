"""작업자 확인 항목 (ConfidenceReport.needs_review)"""

REQUIRED = (  # 로봇 JSON 필수 값 → 없으면 통과(passed)시킬 수 없음
    ("part", "부재·조립 경로를 찾지 못해 확인이 필요합니다"),
    ("welding_condition", "용접 조건을 판별하지 못해 확인이 필요합니다"),
)


def missing_required(context: dict, corrections: list[dict]) -> list[str]:
    """작업자 수정까지 반영해도 비어 있는 필수 값의 확인 대상 (part, welding_condition)"""
    corrected = {c["target"] for c in corrections}
    present = {"part": context["part"]["assembly_path"], "welding_condition": context["welding_condition"]}
    return [target for target, _ in REQUIRED if target not in corrected and not present[target]]


def review_items(vision: dict, context: dict, corrections: list[dict], factors: dict, missing: list[str]) -> list[dict]:
    """작업자가 이미 고치거나 확인한 대상은 넣지 않음"""
    items = [
        {"target": target, "reason": "missing_required", "message": message}
        for target, message in REQUIRED if target in missing
    ]
    # TODO: low_visual_confidence(확률 낮은 표기 + 후보) · 2단계 conflicts(같은 이름의 reason) · vlm_inconsistent
    return items
