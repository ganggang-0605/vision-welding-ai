"""c. 기호·그림 인식: YOLOX

GroundingDINO 제로샷(detect_grounding_dino)은 실험 기록으로만 남김 — PAC 사진에서 쓸 수 없는 수준이라
파이프라인에 연결하지 않음 (vision/reports/phase3_groundingdino.md)
"""
import importlib.util
from dataclasses import asdict, dataclass
from functools import lru_cache

import numpy as np


@dataclass(frozen=True)
class GroundingDinoConfig:
    """찾을 대상을 영어 문구로 적어 학습 없이 검출. prompts: (문구, 사전 code) — 그 문구로 찾은 상자에 code를 붙임.
    문구끼리 단어가 겹치면 어느 문구로 찾았는지 가릴 수 없으니 겹치지 않게 적기"""

    model: str = "IDEA-Research/grounding-dino-tiny"
    prompts: tuple[tuple[str, str], ...] = (("arrow", "→"), ("cross", "+"), ("hole", "unknown"))
    box_threshold: float = 0.3  # 상자 점수가 이보다 낮으면 버림
    text_threshold: float = 0.25  # 문구 단어마다 이 점수를 넘어야 그 상자의 문구로 침

    def models(self) -> dict[str, str]:
        return {"symbol_det": self.model}


DEFAULT_GROUNDING_DINO = GroundingDinoConfig()


def grounding_dino_available() -> bool:
    """torch · transformers(pip install -e "vision[models]")가 깔려 있는지"""
    return all(importlib.util.find_spec(m) is not None for m in ("torch", "transformers"))


def config_dict(config: GroundingDinoConfig) -> dict:
    return {**asdict(config), "prompts": [list(p) for p in config.prompts]}


def detect_symbols(image: np.ndarray) -> list[dict]:
    """VisionResult.symbols 항목에서 id를 뺀 것의 목록 (id는 recognize가 읽는 순서로 붙임).

    필수: label(워크스페이스 사전의 code, 사전에 없으면 "unknown"), prob(0~1), bbox, source("yolox" | "groundingdino" | "vlm")
    선택: candidates
    """
    # TODO: YOLOX 연결
    return []


@lru_cache(maxsize=2)
def _grounding_dino(model_id: str):
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

    return AutoProcessor.from_pretrained(model_id), AutoModelForZeroShotObjectDetection.from_pretrained(model_id).eval()


def detect_grounding_dino(image: np.ndarray, config: GroundingDinoConfig = DEFAULT_GROUNDING_DINO) -> list[dict]:
    """image: OpenCV BGR 배열 → SymbolDetection 목록 (id 없음, source "groundingdino"). 실험 기록용, 파이프라인에서 쓰지 않음"""
    import torch
    from PIL import Image

    processor, model = _grounding_dino(config.model)
    rgb = Image.fromarray(np.ascontiguousarray(image[:, :, ::-1]))
    # GroundingDINO 문구 형식: 소문자, 대상마다 마침표 ("arrow. cross. hole.")
    inputs = processor(images=rgb, text=". ".join(p for p, _ in config.prompts) + ".", return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs)
    result = processor.post_process_grounded_object_detection(
        outputs, inputs.input_ids, threshold=config.box_threshold, text_threshold=config.text_threshold,
        target_sizes=[(rgb.height, rgb.width)],
    )[0]
    phrases = result["text_labels"] if "text_labels" in result else result["labels"]  # transformers 4.5x 이전은 labels
    return to_symbol_detections(phrases, result["scores"].tolist(), result["boxes"].tolist(), config.prompts,
                                (rgb.width, rgb.height))


def phrase_to_code(phrase: str, prompts) -> str | None:
    """GroundingDINO가 돌려준 문구(문구 일부만 오기도 함) → 단어가 가장 많이 겹치는 prompt의 code. 겹치는 게 없으면 None"""
    words = set(phrase.lower().split())
    best = max(((len(words & set(text.lower().split())), code) for text, code in prompts), default=(0, None),
               key=lambda x: x[0])
    return best[1] if best[0] else None


def to_symbol_detections(phrases, scores, boxes, prompts, size: tuple[int, int]) -> list[dict]:
    """GroundingDINO 결과 → SymbolDetection (id 없음). 어느 문구인지 모르는 상자는 버리고, 좌표는 사진 안으로 자름"""
    width, height = size
    detections = []
    for phrase, score, (x1, y1, x2, y2) in zip(phrases, scores, boxes):
        code = phrase_to_code(phrase, prompts)
        bbox = [max(0, int(round(x1))), max(0, int(round(y1))), min(width, int(round(x2))), min(height, int(round(y2)))]
        if code is None or bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
            continue
        detections.append({"label": code, "prob": round(float(score), 4), "bbox": bbox, "source": "groundingdino"})
    return detections
