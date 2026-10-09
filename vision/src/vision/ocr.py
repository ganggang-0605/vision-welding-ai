"""b. 문자 인식: PaddleOCR(검출 + 1차 인식), PARSeq(현장 글씨체), TrOCR(손글씨)"""
import importlib.util
import logging
from dataclasses import asdict, dataclass
from functools import lru_cache

import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class OcrConfig:
    """기본값은 steel-ocr 평가(vision/reports/phase1_baseline.md)에서 고른 조합"""

    det_model: str = "PP-OCRv6_small_det"
    rec_model: str = "PP-OCRv6_medium_rec"
    det_limit_side_len: int = 1280  # 긴 변을 이 크기로 줄여 검출 (원본 4000px 그대로면 느리고 큰 글씨를 쪼갬)
    det_limit_type: str = "max"
    use_textline_orientation: bool = True  # 뒤집힌(180°) 글자 줄 보정 — 쌓아 둔 부재는 표기가 거꾸로 찍히는 경우가 많음
    # Linux CPU 가속(oneDNN). paddlepaddle 3.3.1 + PP-OCRv6 검출 모델은 켜면 Linux에서 바로 오류가 나서 끔 (Mac은 원래 안 씀)
    enable_mkldnn: bool = False
    # 확대 재판독: 찾은 글자 영역을 원본 해상도로 넉넉히 잘라 한 번 더 검출+인식 (긴 변 1280px로 줄여 검출하면 작은 글씨가 뭉개짐)
    zoom_reread: bool = False
    zoom_margin: float = 0.15  # 영역 크기 대비 여백
    zoom_max_side: int = 960  # 잘라낸 영역이 이보다 크면 줄임

    def models(self) -> dict[str, str]:
        return {"ocr_det": self.det_model, "ocr_rec": self.rec_model}


DEFAULT_CONFIG = OcrConfig()


def models_available() -> bool:
    """실제 모델 패키지(pip install -e "vision[models]")가 깔려 있는지. CI·계약 테스트는 모델 없이 돌림"""
    return importlib.util.find_spec("paddleocr") is not None


@lru_cache(maxsize=4)
def _engine(config: OcrConfig):
    from paddleocr import PaddleOCR

    return PaddleOCR(
        text_detection_model_name=config.det_model,
        text_recognition_model_name=config.rec_model,
        text_det_limit_side_len=config.det_limit_side_len,
        text_det_limit_type=config.det_limit_type,
        use_textline_orientation=config.use_textline_orientation,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        enable_mkldnn=config.enable_mkldnn,
    )


@lru_cache(maxsize=1)
def _warn_no_models() -> None:
    log.warning('PaddleOCR이 설치되지 않아 문자 인식을 건너뜁니다 (pip install -e "vision[models]")')


def recognize_text(image: np.ndarray, config: OcrConfig = DEFAULT_CONFIG) -> list[dict]:
    """VisionResult.texts 항목에서 id를 뺀 것의 목록 (id는 recognize가 읽는 순서로 붙임).

    필수: text, prob(0~1), bbox([x1, y1, x2, y2] 원본 좌표), source("paddleocr" | "parseq" | "trocr")
    선택: polygon, style, char_probs(글자 수와 같은 개수), candidates(확률 낮을 때, 첫 번째 = text)
    """
    if not models_available():
        _warn_no_models()
        return []
    result = _engine(config).predict(image)[0]
    detections = to_text_detections(result["rec_texts"], result["rec_scores"], result["rec_polys"])
    if config.zoom_reread:
        detections = [_reread(image, d, config) for d in detections]
    return detections


def _reread(image: np.ndarray, detection: dict, config: OcrConfig) -> dict:
    from vision.recognition import assign_ids  # recognition이 이 모듈을 import하므로 여기서

    zoom = zoom_crop(image, detection["bbox"], config.zoom_margin, config.zoom_max_side)
    if zoom is None:
        return detection
    crop, inner = zoom
    result = _engine(config).predict(crop)[0]
    parts = assign_ids(to_text_detections(result["rec_texts"], result["rec_scores"], result["rec_polys"]), "t")
    return pick_reread(detection, [d for d in parts if _center_inside(d["bbox"], inner)])


def zoom_crop(image: np.ndarray, bbox, margin: float, max_side: int):
    """bbox 주변을 여백과 함께 잘라 (잘린 이미지, 잘린 이미지 좌표의 원래 bbox) 반환. 너무 작으면 None"""
    import cv2

    height, width = image.shape[:2]
    x1, y1, x2, y2 = bbox
    mx, my = (x2 - x1) * margin, (y2 - y1) * margin
    cx1, cy1 = int(max(0, x1 - mx)), int(max(0, y1 - my))
    cx2, cy2 = int(min(width, x2 + mx)), int(min(height, y2 + my))
    if cx2 - cx1 < 8 or cy2 - cy1 < 8:
        return None
    crop = image[cy1:cy2, cx1:cx2]
    scale = min(1.0, max_side / max(crop.shape[:2]))
    if scale < 1:
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    inner = [(x1 - cx1) * scale, (y1 - cy1) * scale, (x2 - cx1) * scale, (y2 - cy1) * scale]
    return crop, inner


def _center_inside(bbox, outer) -> bool:
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


def pick_reread(detection: dict, parts: list[dict]) -> dict:
    """확대 재판독 조각들(읽는 순서)을 이어 붙여, 글자 수로 가중한 평균 확률이 원래보다 높으면 글자·확률만 바꿈 (위치는 그대로)"""
    text = "".join(d["text"] for d in parts)
    if not text:
        return detection
    prob = sum(d["prob"] * len(d["text"]) for d in parts) / len(text)
    if prob <= detection["prob"]:
        return detection
    return {**detection, "text": text, "prob": round(prob, 4)}


def to_text_detections(texts, scores, polys) -> list[dict]:
    """PaddleOCR 결과 → TextDetection (id 없음, 빈 글자 제외)"""
    detections = []
    for text, score, poly in zip(texts, scores, polys):
        text = text.strip()
        if not text:
            continue
        polygon = [[max(0, int(round(x))), max(0, int(round(y)))] for x, y in poly]
        xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
        detections.append({
            "text": text,
            "prob": round(float(score), 4),
            "bbox": [min(xs), min(ys), max(xs), max(ys)],
            "polygon": polygon,
            "source": "paddleocr",
        })
    return detections


def config_dict(config: OcrConfig = DEFAULT_CONFIG) -> dict:
    return asdict(config)
