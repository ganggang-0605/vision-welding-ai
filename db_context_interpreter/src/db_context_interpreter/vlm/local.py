"""로컬 Qwen3-VL · InternVL — OpenAI 호환 서버(vLLM 등)로 띄워 VLM_BASE_URL로 연결 (기본 http://localhost:8001/v1).
출력 토큰 확률(logprobs)을 받아 token_prob로 씀"""
import os

from db_context_interpreter.vlm.gpt import chat


def generate(system: str, prompt: str, image: tuple[bytes, str] | None, model: str) -> tuple[str, float | None]:
    from openai import OpenAI

    client = OpenAI(base_url=os.environ.get("VLM_BASE_URL", "http://localhost:8001/v1"),
                    api_key=os.environ.get("VLM_API_KEY", "EMPTY"))
    return chat(client, system, prompt, image, model, logprobs=True)
