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
    return to_text_detections(result["rec_texts"], result["rec_scores"], result["rec_polys"])


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
