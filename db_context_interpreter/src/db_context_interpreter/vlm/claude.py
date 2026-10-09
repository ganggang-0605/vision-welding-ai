"""Claude (Anthropic API) — ANTHROPIC_API_KEY. 출력 토큰 확률을 주지 않으므로 token_prob는 None"""
import base64

from db_context_interpreter.vlm.prompt import RESPONSE_SCHEMA


def generate(system: str, prompt: str, image: tuple[bytes, str] | None, model: str) -> tuple[str, float | None]:
    import anthropic

    content = []
    if image:
        data, media_type = image
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": media_type, "data": base64.standard_b64encode(data).decode("ascii"),
        }})
    content.append({"type": "text", "text": prompt})
    response = anthropic.Anthropic().beta.messages.create(
        model=model,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": content}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}},
        # 안전 분류기가 거절하면 서버가 다른 모델로 다시 시도
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude가 응답을 거절함: {response.stop_details}")
    return next(b.text for b in response.content if b.type == "text"), None
