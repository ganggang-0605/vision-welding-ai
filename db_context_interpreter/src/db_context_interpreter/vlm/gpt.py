"""GPT (OpenAI API) — OPENAI_API_KEY. OpenAI 호환 서버(로컬 vLLM 등)도 base_url만 바꿔 같은 함수를 씀 (local.py)"""
import base64
import math


def generate(system: str, prompt: str, image: tuple[bytes, str] | None, model: str) -> tuple[str, float | None]:
    from openai import OpenAI

    return chat(OpenAI(), system, prompt, image, model, logprobs=False)


def chat(client, system: str, prompt: str, image: tuple[bytes, str] | None, model: str, *, logprobs: bool) -> tuple[str, float | None]:
    """chat.completions JSON 응답. logprobs=True면 출력 토큰 확률의 기하평균을 token_prob로"""
    content = []
    if image:
        data, media_type = image
        url = f"data:{media_type};base64,{base64.standard_b64encode(data).decode('ascii')}"
        content.append({"type": "image_url", "image_url": {"url": url}})
    content.append({"type": "text", "text": prompt})
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
        response_format={"type": "json_object"},
        **({"logprobs": True} if logprobs else {}),
    )
    choice = response.choices[0]
    token_prob = None
    if logprobs and choice.logprobs and choice.logprobs.content:
        values = [t.logprob for t in choice.logprobs.content]
        token_prob = round(math.exp(sum(values) / len(values)), 4)
    return choice.message.content, token_prob
