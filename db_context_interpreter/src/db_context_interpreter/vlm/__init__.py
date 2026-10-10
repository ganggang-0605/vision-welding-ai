"""d. VLM 맥락 해석 — .env의 VLM_PROVIDER(claude | gpt | gemini | qwen3-vl | internvl)로 고름

provider별 구현은 이 폴더의 claude.py · gpt.py · gemini.py · local.py.
SDK는 함수 안에서 import (기본 설치에는 없음, pip install -e "db_context_interpreter[vlm]").

환경 변수
- VLM_PROVIDER: 비어 있거나 none · off면 VLM을 쓰지 않음 (ContextResult.vlm = null)
- VLM_MODEL: 모델 이름 (없으면 DEFAULT_MODELS)
- VLM_RUNS: 같은 입력으로 추론할 횟수 (기본 3, 동시에 보냄) → consistency. 1이면 consistency = null
- VLM_BASE_URL · VLM_API_KEY: 로컬 모델(qwen3-vl · internvl)의 OpenAI 호환 서버
"""
import logging
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
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
    """run_vlm의 결과만 (실패 이유는 버림)"""
    return run_vlm(vision_result, context_input, image)[0]


def run_vlm(vision_result: dict, context_input: dict, image=None) -> tuple[VlmOutput | None, str | None]:
    """(VlmOutput | None, 실패 이유 | None). VlmOutput = VlmResult (provider, model, interpretation, image_attached, reading,
    token_prob, consistency, runs) + 표기별 의미. VLM을 안 쓰면 (None, None).

    image: 원본 사진 (인코딩된 bytes · 파일 경로 · numpy 배열). 없으면 vision_result의
    preprocessed_image_uri(로컬 파일), 그것도 없으면 사진 없이 1단계 결과와 DB만으로 해석.
    보낸 사진 크기가 원본과 다르면(줄이기 · 키우기) 프롬프트의 좌표는 보낸 사진 기준으로 바꾸고, 응답 bbox는 원본 좌표로 되돌림.
    reading: VLM이 이미지에서 직접 읽은 글자·기호. 1단계 결과에 대응하면 그 ID(t*, s*),
    1단계가 놓친 표기면 v1, v2, … — context_input["previous_reading"]에 같은 표기가 있으면 그 v* ID를 그대로 씀.
    VLM_RUNS번을 동시에 보내고, 모두 실패하면 경고를 남기고 (None, 이유) — VLM 없이 해석을 이어 감
    """
    provider = os.environ.get("VLM_PROVIDER", "").split("#")[0].strip().lower()
    if provider in ("", "none", "off"):
        return None, None
    if provider not in PROVIDERS:
        raise ValueError(f"VLM_PROVIDER '{provider}'를 모름 (가능한 값: {', '.join(PROVIDERS)})")
    model = os.environ.get("VLM_MODEL") or DEFAULT_MODELS[provider]
    runs = max(1, int(os.environ.get("VLM_RUNS", 3)))
    picture = load_image(image, vision_result)
    original = vision_result["image_size"]
    sent = encoded_size(picture[0]) if picture else None
    scale = (original["width"] / sent[0], original["height"] / sent[1]) if sent else (1.0, 1.0)
    prompt = build_prompt(vision_result, context_input, picture is not None,
                          {"width": sent[0], "height": sent[1]} if sent else None)

    def call() -> tuple[str, float | None]:
        return PROVIDERS[provider](SYSTEM, prompt, picture, model)

    outputs: list[tuple[dict, float | None]] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=runs) as pool:
        for future in [pool.submit(call) for _ in range(runs)]:
            try:
                text, token_prob = future.result()
                outputs.append((parse_response(text), token_prob))
            except Exception as e:  # SDK 미설치 · API 키 없음 · 네트워크 · 형식 오류
                log.warning("VLM(%s) 추론 실패: %s", provider, e)
                errors.append(f"{type(e).__name__}: {e}")
    if not outputs:
        return None, f"{provider}({model}) 추론 {runs}번 모두 실패 — {errors[0]}"[:500]
    output = combine(outputs, provider, model, vision_result, context_input, scale)
    output.result["image_attached"] = picture is not None
    return output, None


def combine(outputs: list[tuple[dict, float | None]], provider: str, model: str, vision_result: dict, context_input: dict,
            scale: tuple[float, float] = (1.0, 1.0)) -> VlmOutput:
    """여러 번 추론한 결과 → 다른 추론과 표기 단위로 가장 많이 겹치는 읽기를 고르고(consensus_index),
    읽기 전체가 같은 비율을 consistency로 (신뢰도는 보수적으로)"""
    resolved = [resolve(out, vision_result, context_input, scale) for out, _ in outputs]
    keys = [reading_key(reading) for reading, _ in resolved]
    count = Counter(keys).most_common(1)[0][1]
    index = consensus_index(keys)
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


def resolve(out: dict, vision_result: dict, context_input: dict,
            scale: tuple[float, float] = (1.0, 1.0)) -> tuple[dict, dict[str, str]]:
    """VLM 응답의 ref_id 정리: 1단계에 있는 t*·s*는 그대로, 나머지(new1 …·모르는 ID)는 v* (이전 revision의 같은 표기면 같은 v*).
    bbox는 보낸 사진 좌표 → 원본 좌표 (scale = 원본 / 보낸 사진)"""
    width, height = vision_result["image_size"]["width"], vision_result["image_size"]["height"]
    known = {"texts": {t["id"] for t in vision_result["texts"]}, "symbols": {s["id"] for s in vision_result["symbols"]}}
    previous = context_input["previous_reading"] or {"texts": [], "symbols": []}
    previous_ids = {
        (kind, normalize(x["text" if kind == "texts" else "label"])): x["ref_id"]
        for kind in ("texts", "symbols") for x in previous[kind] if x["ref_id"][0] == "v"
    }
    used = {int(v[1:]) for v in previous_ids.values()}
    echoes = corrected_values(context_input)
    aliases: dict[str, str] = {}  # 응답의 임시 ID(new1 …) → 붙인 ID
    reading: dict[str, list] = {"texts": [], "symbols": []}
    seen: set[str] = set()

    for kind, field in (("texts", "text"), ("symbols", "label")):
        for item in out.get(kind, []):
            value = str(item.get(field) or "").strip()
            if not value:
                continue
            ref = str(item.get("ref_id") or "")
            if ref not in known[kind] and not valid_bbox(item.get("bbox")) and (kind, normalize(value)) in echoes:
                continue  # 작업자 수정을 사진에서 읽은 것처럼 옮겨 적은 것 — 위치가 없으면 읽기가 아님
            if ref not in known[kind] or ref in seen:
                ref = previous_ids.get((kind, normalize(value)))
                if ref is None or ref in seen:
                    ref = f"v{next_free(used)}"
                aliases[str(item.get("ref_id") or "")] = ref
            seen.add(ref)
            entry = {field: value, "ref_id": ref}
            bbox = item.get("bbox")
            if valid_bbox(bbox):
                if scale == (1.0, 1.0):
                    entry["bbox"] = list(bbox)
                else:
                    x1, y1, x2, y2 = bbox
                    entry["bbox"] = [min(round(x1 * scale[0]), width), min(round(y1 * scale[1]), height),
                                     min(round(x2 * scale[0]), width), min(round(y2 * scale[1]), height)]
            reading[kind].append(entry)

    keep_corrected_vlm_ids(reading, previous, context_input, seen)
    meanings = {}
    for m in out.get("meanings", []):
        ref = aliases.get(str(m.get("ref_id")), str(m.get("ref_id")))
        if ref in seen and isinstance(m.get("meaning"), str) and m["meaning"].strip():
            meanings[ref] = m["meaning"].strip()
    return reading, meanings


def valid_bbox(bbox) -> bool:
    return isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(n, int | float) and n >= 0 for n in bbox)


def corrected_values(context_input: dict) -> set[tuple[str, str]]:
    """작업자가 고친 셀 형태·각장 값 {(texts | symbols, 정규화한 값)} — VLM이 이 값을 사진에서 읽은 것처럼 되돌려주는지 가리는 데 씀"""
    values = set()
    for c in context_input["corrections"]:
        if c["target"] == "cell":
            values |= {("symbols", normalize(label)) for side in ("left", "right") for label in c["value"][side]}
        elif c["target"] == "leg_lengths":
            values |= {("texts", normalize(leg["raw_text"])) for leg in c["value"] if leg.get("raw_text")}
    return values


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


def consensus_index(keys: list[tuple]) -> int:
    """표기 단위 다수결: 각 추론의 표기마다 같은 표기를 읽은 다른 추론 수를 더하고, 혼자만 읽은 표기는 1씩 뺌 → 가장 높은 추론.
    읽기 전체가 같은 추론이 여럿이면 그쪽이 자연히 높음. 동점이면 먼저 나온 것.
    (전체 일치만 보면 화살표 하나만 달라도 셋 다 달라져 첫 추론을 쓰게 됨 — 예: F5.5 · F7.5 · F5.5 에서 F7.5)"""
    counts = Counter(item for key in keys for item in set(key))
    scores = [sum(counts[item] - 1 for item in set(key)) - sum(counts[item] == 1 for item in set(key)) for key in keys]
    return scores.index(max(scores))


def reading_key(reading: dict) -> tuple:
    """추론끼리 같은 읽기인지 비교하는 키 (위치·순서 무시). VLM만 읽은 표기의 v* 번호는 추론마다 붙는 순서가 달라
    번호는 빼고 글자만 비교 (같은 표기를 다른 순서로 읽었다고 불일치로 세지 않게)"""
    return tuple(sorted(
        (kind, "v" if x["ref_id"][0] == "v" else x["ref_id"], normalize(x.get("text") or x.get("label")))
        for kind in ("texts", "symbols") for x in reading[kind]
    ))


def load_image(image, vision_result: dict) -> tuple[bytes, str] | None:
    """(인코딩된 이미지 bytes, media type) 또는 None. 너무 큰 사진은 VLM 에 보낼 수 있게 줄인다 (fit_for_vlm)"""
    if image is None:
        uri = vision_result["preprocess"].get("preprocessed_image_uri")
        path = Path(uri.removeprefix("file://")) if uri else None
        if path is None or not path.is_file():
            return None
        image = path
    if isinstance(image, str | Path):
        path = Path(image)
        return fit_for_vlm(path.read_bytes(), MEDIA_TYPES.get(path.suffix.lower(), "image/jpeg"))
    if isinstance(image, bytes | bytearray):
        data = bytes(image)
        return fit_for_vlm(data, "image/png" if data.startswith(b"\x89PNG") else "image/jpeg")
    import cv2  # numpy 배열 (backend가 넘기는 형식, BGR)

    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("이미지를 PNG로 인코딩하지 못함")
    return fit_for_vlm(encoded.tobytes(), "image/png", image)


# provider 이미지 한도: Claude 10MB(요청 본문은 base64 라 더 큼) · 긴 변 1568px 넘으면 Claude 가 알아서 줄임.
# 휴대폰 원본(4000px PNG 30MB 등)은 그대로 보내면 400 오류라, 넘으면 긴 변 1568px JPEG 로 줄여 보낸다.
# 반대로 운영측 손글씨 예시(343px)처럼 작은 사진은 VLM 이 숫자를 틀려서(F5.0 → F6.0) 긴 변 1024px 로 키워 보낸다.
# 크기를 바꾸면 run_vlm 이 프롬프트 좌표와 응답 bbox 를 그 배율로 맞춘다.
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_IMAGE_SIDE = 1568
MIN_IMAGE_SIDE = 512
UPSCALE_SIDE = 1024


def fit_for_vlm(data: bytes, media_type: str, decoded=None) -> tuple[bytes, str]:
    """크기·용량 한도 안이면 그대로. 넘으면 긴 변 MAX_IMAGE_SIDE 의 JPEG(품질 90), 긴 변이 MIN_IMAGE_SIDE 보다 작으면
    긴 변 UPSCALE_SIDE 의 PNG 로 다시 인코딩. OpenCV 가 없으면(이 패키지만 설치한 CI 등) 그대로 보낸다
    — backend 는 vision 패키지와 함께 OpenCV 가 깔려 있음"""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return data, media_type

    image = decoded if decoded is not None else cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:  # 읽을 수 없는 형식이면 손대지 않고 provider 에 맡김
        return data, media_type
    height, width = image.shape[:2]
    if max(height, width) < MIN_IMAGE_SIDE:
        scale = UPSCALE_SIDE / max(height, width)
        image = cv2.resize(image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_CUBIC)
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise ValueError("이미지를 PNG로 인코딩하지 못함")
        return encoded.tobytes(), "image/png"
    if len(data) <= MAX_IMAGE_BYTES and max(height, width) <= MAX_IMAGE_SIDE:
        return data, media_type
    scale = min(1.0, MAX_IMAGE_SIDE / max(height, width))
    if scale < 1.0:
        image = cv2.resize(image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise ValueError("이미지를 JPEG로 인코딩하지 못함")
    return encoded.tobytes(), "image/jpeg"


def encoded_size(data: bytes) -> tuple[int, int] | None:
    """인코딩된 사진의 (가로, 세로). OpenCV 가 없거나 읽을 수 없으면 None (좌표 배율을 맞추지 않음)"""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    return (image.shape[1], image.shape[0]) if image is not None else None
