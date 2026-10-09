"""[3단계] 진입점: 근거 값(factors) → 세 신뢰도 → 통과 여부 · 판단 근거 · 작업자 확인 항목"""
from calculate_reliability.db_consistency import db_consistency_factors, db_consistency_score
from calculate_reliability.review import evidence, missing_required, review_items
from calculate_reliability.visual import visual_factors, visual_score
from calculate_reliability.vlm_reasoning import vlm_reasoning_factors, vlm_reasoning_score


def score(vision: dict, context: dict, corrections: list[dict], threshold: float) -> dict:
    """VisionResult + ContextResult + 작업자 수정(Analysis.corrections) → ConfidenceReport.
    threshold는 .env의 CONFIDENCE_THRESHOLD (0~100). 작업자가 고치거나 확인한 항목은 확인된 것으로 봄"""
    factors = {
        "visual": visual_factors(vision, context, corrections),
        "db_consistency": db_consistency_factors(context, corrections),
        "vlm_reasoning": vlm_reasoning_factors(context),
    }
    visual = visual_score(factors["visual"])
    db_consistency = db_consistency_score(factors["db_consistency"])
    vlm_reasoning = vlm_reasoning_score(factors["vlm_reasoning"], context["vlm"] is not None, bool(context.get("vlm_error")))
    overall = min(visual, db_consistency, vlm_reasoning)
    missing = missing_required(context, corrections)
    passed = overall >= threshold and not missing
    return {
        "visual": visual,
        "db_consistency": db_consistency,
        "vlm_reasoning": vlm_reasoning,
        "overall": overall,
        "threshold": threshold,
        "passed": passed,
        "factors": factors,
        "evidence": evidence(vision, context, corrections, factors),
        "needs_review": review_items(vision, context, corrections, factors, missing, threshold, passed),
    }
