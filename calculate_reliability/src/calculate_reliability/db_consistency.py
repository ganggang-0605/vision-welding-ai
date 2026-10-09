"""b. DB 정합성 신뢰도: 문자/기호 사전 규칙, 조립 트리 내 부재 존재 여부, 표준 용접 기준과의 충돌"""

RULE_MATCHES = frozenset({"exact", "alias", "candidate"})  # 사전 규칙에 맞는 대조 (fuzzy · vlm · none은 아님)


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
        "dictionary_match_rate": round(sum(m["match"] in RULE_MATCHES for m in matches) / len(matches), 2) if matches else None,
        "part_found": part_found,
        "standard_conflicts": sum(1 for c in context["conflicts"] if c["type"] == "standard_conflict"),
    }


def db_consistency_score(factors: dict) -> float:
    """0~100. TODO: 사전 대조 비율 · 부재 존재 · 기준 충돌 감점 (가중치는 조정 예정)"""
    return 0.0
