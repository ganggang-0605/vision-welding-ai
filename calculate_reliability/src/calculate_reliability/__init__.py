"""[3단계] 신뢰도 산출 — score(vision, context, corrections, threshold) → ConfidenceReport

시각 인식(visual.py) / DB 정합성(db_consistency.py) / VLM 추론(vlm_reasoning.py) 신뢰도를 0~100으로 내고,
overall = 셋 중 최솟값. 작업자 확인 항목은 review.py.
"""
from calculate_reliability.score import score

__all__ = ["score"]
