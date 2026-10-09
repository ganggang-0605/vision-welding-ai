"""c. VLM 추론 신뢰도: 출력 토큰 확률, 다중 추론 일관성"""


def vlm_reasoning_factors(context: dict) -> dict:
    vlm = context["vlm"]
    return {
        "token_prob": vlm["token_prob"] if vlm else None,
        "consistency": vlm["consistency"] if vlm else None,
    }


def vlm_reasoning_score(factors: dict) -> float:
    """0~100. TODO: 토큰 확률(없으면 일관성만) (가중치는 조정 예정)"""
    return 0.0
