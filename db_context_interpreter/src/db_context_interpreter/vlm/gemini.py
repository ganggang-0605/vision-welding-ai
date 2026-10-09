"""Gemini (Google GenAI) — GEMINI_API_KEY. token_prob는 None"""
import os


def generate(system: str, prompt: str, image: tuple[bytes, str] | None, model: str) -> tuple[str, float | None]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    contents = []
    if image:
        data, media_type = image
        contents.append(types.Part.from_bytes(data=data, mime_type=media_type))
    contents.append(prompt)
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json"),
    )
    return response.text, None
