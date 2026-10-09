"""b. DB 정합성 신뢰도: 문자/기호 사전 규칙, 조립 트리 내 부재 존재 여부, 표준 용접 기준과의 충돌"""

RULE_MATCHES = frozenset({"exact", "alias", "candidate"})  # 사전 규칙에 맞는 대조 (fuzzy · vlm은 아님)
UNMATCHED_WEIGHT = 25  # 사전 규칙에 안 맞는 표기 비율 1당 감점
PART_NOT_FOUND = 40    # 부재가 조립 트리에 없음
STANDARD_CONFLICT = 20  # 표준 용접 기준과 충돌 1건 (warning · error)


def is_rule_match(m: dict) -> bool:
    """사전 대조 · 표기 규칙(판 두께 t=10, 치수 350)으로 해석한 표기. fuzzy · vlm · 해석 못 한 none은 아님"""
    return m["match"] in RULE_MATCHES or (m["match"] == "none" and m["meaning"] is not None)


def db_consistency_factors(context: dict, corrections: list[dict]) -> dict:
    matches = context["dictionary_matches"]
    part = context["part"]
    if any(c["target"] == "part" for c in corrections):
        part_found = True  # 작업자가 조립 경로를 정함
    elif part["node_id"] is None and part["assembly_path"] is None:
        part_found = None  # 부재 표기를 못 찾음 → 판단할 수 없음
    else:
        part_found = part["found_in_tree"]
    return {
        "dictionary_match_rate": round(sum(is_rule_match(m) for m in matches) / len(matches), 2) if matches else None,
        "part_found": part_found,
        "standard_conflicts": sum(1 for c in context["conflicts"]
                                  if c["type"] == "standard_conflict" and c["severity"] != "info"),
    }


def db_consistency_score(factors: dict) -> float:
    """0~100 = 100 − 사전 규칙에 안 맞는 비율 × 25 − 부재가 트리에 없으면 40 − 기준 충돌 1건당 20"""
    score = 100.0
    if factors["dictionary_match_rate"] is not None:
        score -= UNMATCHED_WEIGHT * (1 - factors["dictionary_match_rate"])
    if factors["part_found"] is False:
        score -= PART_NOT_FOUND
    score -= STANDARD_CONFLICT * factors["standard_conflicts"]
    return round(min(100.0, max(0.0, score)))
