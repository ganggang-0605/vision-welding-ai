"""d. VLM 맥락 해석 — .env의 VLM_PROVIDER(claude | gpt | gemini | qwen3-vl | internvl)로 고름

provider별 구현은 이 폴더에 claude.py · gpt.py · gemini.py · local.py로 추가하고,
SDK는 함수 안에서 import (기본 설치에는 없음, pip install -e "db_context_interpreter[vlm]").
"""


def interpret_with_vlm(vision_result: dict, context_input: dict) -> dict | None:
    """VlmResult (provider, model, interpretation, reading, token_prob, consistency, runs). VLM을 안 쓰면 None.

    reading: VLM이 이미지에서 직접 읽은 글자·기호. 1단계 결과에 대응하면 그 ID(t*, s*),
    1단계가 놓친 표기면 v1, v2, … — context_input["previous_reading"]에 같은 표기가 있으면 그 v* ID를 그대로 씀
    """
    # TODO: provider 연결
    return None
