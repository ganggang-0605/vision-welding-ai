"""c. VLM 추론 신뢰도: 출력 토큰 확률, 다중 추론 일관성"""

CONSISTENCY_ONLY_CAP = 0.9  # 토큰 확률을 주지 않는 모델(Claude)은 일관성이 1이어도 90
SINGLE_RUN = 60.0           # 추론 1번 + 토큰 확률 없음 → 잴 수 없음 (작업자 확인)


def vlm_reasoning_factors(context: dict) -> dict:
    vlm = context["vlm"]
    return {
        "token_prob": vlm["token_prob"] if vlm else None,
        "consistency": vlm["consistency"] if vlm else None,
    }


def vlm_reasoning_score(factors: dict, used: bool, failed: bool) -> float:
    """0~100. used: VLM 결과가 있음, failed: VLM을 켰는데 추론이 모두 실패함 (ContextResult.vlm_error).
    VLM을 끈 경우는 이 층을 판단에서 빼려고 100 (overall은 세 신뢰도의 최솟값)"""
    if failed:
        return 0.0
    if not used:
        return 100.0
    token, consistency = factors["token_prob"], factors["consistency"]
    if token is not None and consistency is not None:
        return round(100 * (token + consistency) / 2)
    if token is not None:
        return round(100 * token)
    if consistency is not None:
        return round(100 * CONSISTENCY_ONLY_CAP * consistency)
    return SINGLE_RUN
