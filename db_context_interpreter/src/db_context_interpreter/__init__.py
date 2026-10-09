"""[2단계] DB 기반 맥락 해석 — interpret(vision_result, context_input) → ContextResult

- 용접 기준 DB: 표준 용접 기준표 대조 (welding.py)
- 문자/기호 DB: 워크스페이스 사전 대조 (dictionary.py)
- 조립 경로 DB: 블록→대조립→중조립→소조립→부재 경로 추적 (assembly.py)
- VLM: Qwen3-VL·InternVL(로컬) / Gemini·GPT·Claude(상용) (vlm/)

DB는 직접 읽지 않고 백엔드가 넘겨 준 ContextInput(shared/schemas/context_input.schema.json)만 씀.
"""
from db_context_interpreter.interpret import interpret

__all__ = ["interpret"]
