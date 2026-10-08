"""DB 기반 맥락 해석
- 용접 기준 DB: 표준 용접 기준표 대조
- 문자/기호 DB: 워크스페이스 사전 대조
- 조립 경로 DB: 블록→대조립→중조립→소조립→부재 경로 추적
- VLM: Qwen3-VL·InternVL(로컬) / Gemini·GPT·Claude(상용)
"""


def interpret_context(image, texts: list[dict], symbols: list[dict], workspace_id: str) -> dict:
    # TODO
    return {
        "vlm_reading": None,
        "assembly_path": None,
        "welding_condition": None,
        "conflicts": [],
        "vlm_token_prob": None,
        "vlm_consistency": None,
    }
