"""d. VLM 맥락 해석 — .env의 VLM_PROVIDER(claude | gpt | gemini | qwen3-vl | internvl)로 고름

provider별 구현은 이 폴더의 claude.py · gpt.py · gemini.py · local.py.
SDK는 함수 안에서 import (기본 설치에는 없음, pip install -e "db_context_interpreter[vlm]").

환경 변수
- VLM_PROVIDER: 비어 있거나 none · off면 VLM을 쓰지 않음 (ContextResult.vlm = null)
- VLM_MODEL: 모델 이름 (없으면 DEFAULT_MODELS)
- VLM_RUNS: 같은 입력으로 추론할 횟수 (기본 3) → consistency. 1이면 consistency = null
- VLM_BASE_URL · VLM_API_KEY: 로컬 모델(qwen3-vl · internvl)의 OpenAI 호환 서버
"""
import logging
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from db_context_interpreter.readings import normalize
from db_context_interpreter.vlm import claude, gemini, gpt, local
from db_context_interpreter.vlm.prompt import SYSTEM, build_prompt, parse_response

log = logging.getLogger(__name__)

PROVIDERS = {
    "claude": claude.generate,
    "gpt": gpt.generate,
    "gemini": gemini.generate,
    "qwen3-vl": local.generate,
    "internvl": local.generate,
}
DEFAULT_MODELS = {
    "claude": "claude-opus-5-5",
    "gpt": "gpt-5",
    "gemini": "gemini-2.5-flash",
    "qwen3-vl": "Qwen/Qwen3-VL-8B-Instruct",
    "internvl": "OpenGVLab/InternVL3-8B",
}
DEFAULT_PROB = 0.5  # 토큰 확률·일관성을 모두 모를 때 VLM 해석에 주는 점수
MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}


@dataclass
class VlmOutput:
    result: dict              # ContextResult.vlm (VlmResult)
    meanings: dict[str, str]  # 사전에 없는 표기의 VLM 해석 {ref_id: 의미} → DictionaryMatch(match="vlm")

    @property
    def prob(self) -> float:
        """VLM 해석의 확률 0~1 (토큰 확률 → 다중 추론 일관성 → 기본값 순)"""
        for value in (self.result["token_prob"], self.result["consistency"]):
            if value is not None:
                return value
        return DEFAULT_PROB


def interpret_with_vlm(vision_result: dict, context_input: dict, image=None) -> VlmOutput | None:
    """VlmResult (provider, model, interpretation, reading, token_prob, consistency, runs) + 표기별 의미. VLM을 안 쓰면 None.

    image: 원본 사진 (인코딩된 bytes · 파일 경로 · numpy 배열). 없으면 vision_result의 preprocessed_image_uri(로컬 파일),
    그것도 없으면 사진 없이 1단계 결과와 DB만으로 해석.
    reading: VLM이 이미지에서 직접 읽은 글자·기호. 1단계 결과에 대응하면 그 ID(t*, s*),
    1단계가 놓친 표기면 v1, v2, … — context_input["previous_reading"]에 같은 표기가 있으면 그 v* ID를 그대로 씀.
    provider 호출이 모두 실패하면 경고를 남기고 None (VLM 없이 해석을 이어 감)
    """
    provider = os.environ.get("VLM_PROVIDER", "").split("#")[0].strip().lower()
    if provider in ("", "none", "off"):
        return None
    if provider not in PROVIDERS:
        raise ValueError(f"VLM_PROVIDER '{provider}'를 모름 (가능한 값: {', '.join(PROVIDERS)})")
    model = os.environ.get("VLM_MODEL") or DEFAULT_MODELS[provider]
    runs = max(1, int(os.environ.get("VLM_RUNS", 3)))
    picture = load_image(image, vision_result)
    prompt = build_prompt(vision_result, context_input, picture is not None)

    outputs: list[tuple[dict, float | None]] = []
    for _ in range(runs):
        try:
            text, token_prob = PROVIDERS[provider](SYSTEM, prompt, picture, model)
            outputs.append((parse_response(text), token_prob))
        except Exception as e:  # SDK 미설치 · API 키 없음 · 네트워크 · 형식 오류
            log.warning("VLM(%s) 추론 실패: %s", provider, e)
    if not outputs:
        return None
    return combine(outputs, provider, model, vision_result, context_input)


def combine(outputs: list[tuple[dict, float | None]], provider: str, model: str, vision_result: dict, context_input: dict) -> VlmOutput:
    """여러 번 추론한 결과 → 가장 많이 나온 읽기를 고르고 일치 비율을 consistency로"""
    resolved = [resolve(out, vision_result, context_input) for out, _ in outputs]
    keys = [reading_key(reading) for reading, _ in resolved]
    majority, count = Counter(keys).most_common(1)[0]
    index = keys.index(majority)
    reading, meanings = resolved[index]
    probs = [p for _, p in outputs if p is not None]
    return VlmOutput(
        result={
            "provider": provider,
            "model": model,
            "interpretation": outputs[index][0]["interpretation"].strip(),
            "reading": reading,
            "token_prob": round(sum(probs) / len(probs), 4) if probs else None,
            "consistency": round(count / len(outputs), 2) if len(outputs) > 1 else None,
            "runs": len(outputs),
        },
        meanings=meanings,
    )


def resolve(out: dict, vision_result: dict, context_input: dict) -> tuple[dict, dict[str, str]]:
    """VLM 응답의 ref_id 정리: 1단계에 있는 t*·s*는 그대로, 나머지(new1 …·모르는 ID)는 v* (이전 revision의 같은 표기면 같은 v*)"""
    known = {"texts": {t["id"] for t in vision_result["texts"]}, "symbols": {s["id"] for s in vision_result["symbols"]}}
    previous = context_input["previous_reading"] or {"texts": [], "symbols": []}
    previous_ids = {
        (kind, normalize(x["text" if kind == "texts" else "label"])): x["ref_id"]
        for kind in ("texts", "symbols") for x in previous[kind] if x["ref_id"][0] == "v"
    }
    used = {int(v[1:]) for v in previous_ids.values()}
    aliases: dict[str, str] = {}  # 응답의 임시 ID(new1 …) → 붙인 ID
    reading: dict[str, list] = {"texts": [], "symbols": []}
    seen: set[str] = set()

    for kind, field in (("texts", "text"), ("symbols", "label")):
        for item in out.get(kind, []):
            value = str(item.get(field) or "").strip()
            if not value:
                continue
            ref = str(item.get("ref_id") or "")
            if ref not in known[kind] or ref in seen:
                ref = previous_ids.get((kind, normalize(value)))
                if ref is None or ref in seen:
                    ref = f"v{next_free(used)}"
                aliases[str(item.get("ref_id") or "")] = ref
            seen.add(ref)
            entry = {field: value, "ref_id": ref}
            bbox = item.get("bbox")
            if isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(n, int | float) and n >= 0 for n in bbox):
                entry["bbox"] = list(bbox)
            reading[kind].append(entry)

    keep_corrected_vlm_ids(reading, previous, context_input, seen)
    meanings = {}
    for m in out.get("meanings", []):
        ref = aliases.get(str(m.get("ref_id")), str(m.get("ref_id")))
        if ref in seen and isinstance(m.get("meaning"), str) and m["meaning"].strip():
            meanings[ref] = m["meaning"].strip()
    return reading, meanings


def keep_corrected_vlm_ids(reading: dict, previous: dict, context_input: dict, seen: set[str]) -> None:
    """작업자가 고친 v*는 이번 추론이 다시 읽지 못했어도 남김 (corrections가 가리키는 ID가 사라지지 않게)"""
    targets = {c["target"] for c in context_input["corrections"]}
    for kind in ("texts", "symbols"):
        for x in previous[kind]:
            if x["ref_id"][0] == "v" and x["ref_id"] in targets and x["ref_id"] not in seen:
                reading[kind].append(dict(x))
                seen.add(x["ref_id"])


def next_free(used: set[int]) -> int:
    n = 1
    while n in used:
        n += 1
    used.add(n)
    return n


def reading_key(reading: dict) -> tuple:
    """추론끼리 같은 읽기인지 비교하는 키 (위치·순서 무시)"""
    return tuple(sorted(
        (kind, x["ref_id"], normalize(x.get("text") or x.get("label")))
        for kind in ("texts", "symbols") for x in reading[kind]
    ))


def load_image(image, vision_result: dict) -> tuple[bytes, str] | None:
    """(인코딩된 이미지 bytes, media type) 또는 None"""
    if image is None:
        uri = vision_result["preprocess"].get("preprocessed_image_uri")
        path = Path(uri.removeprefix("file://")) if uri else None
        if path is None or not path.is_file():
            return None
        image = path
    if isinstance(image, str | Path):
        path = Path(image)
        return path.read_bytes(), MEDIA_TYPES.get(path.suffix.lower(), "image/jpeg")
    if isinstance(image, bytes | bytearray):
        data = bytes(image)
        return data, "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"
    import cv2  # numpy 배열 (backend가 넘기는 형식, BGR)

    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("이미지를 PNG로 인코딩하지 못함")
    return encoded.tobytes(), "image/png"
