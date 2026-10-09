"""[1단계] 진입점: 전처리 → 문자 인식 / 기호 인식 → ID 붙이기"""
import time

import numpy as np

from vision.ocr import DEFAULT_CONFIG as OCR_CONFIG
from vision.ocr import models_available, recognize_text
from vision.preprocess import preprocess
from vision.symbols import detect_symbols


def recognize(image: np.ndarray, image_id: str) -> dict:
    """image: OpenCV BGR 배열 (H, W, 3) → VisionResult. bbox는 원본 이미지 좌표"""
    start = time.perf_counter()
    height, width = image.shape[:2]
    clean, prep = preprocess(image)
    texts = recognize_text(clean)
    symbols = detect_symbols(clean)
    return {
        "image_id": image_id,
        "image_size": {"width": width, "height": height},
        "preprocess": prep,
        "texts": assign_ids(texts, "t"),
        "symbols": assign_ids(symbols, "s"),
        "models": OCR_CONFIG.models() if models_available() else {},  # TODO: 기호 검출기 연결 시 추가
        "elapsed_ms": int((time.perf_counter() - start) * 1000),
    }


def assign_ids(detections: list[dict], prefix: str) -> list[dict]:
    """읽는 순서(줄 단위로 위→아래, 줄 안에서 왼→오른)로 정렬하고 t1, t2, … / s1, s2, …를 붙임.
    이 ID는 2·3단계와 GUI가 글자·기호를 가리키는 기준이라, 작업이 끝날 때까지 바뀌면 안 됨"""
    lines: list[list] = []  # [중심 y, 높이, [검출 결과]]
    for d in sorted(detections, key=lambda d: (d["bbox"][1] + d["bbox"][3]) / 2):
        center, height = (d["bbox"][1] + d["bbox"][3]) / 2, d["bbox"][3] - d["bbox"][1]
        if lines and abs(center - lines[-1][0]) <= lines[-1][1] / 2:
            lines[-1][2].append(d)
        else:
            lines.append([center, height, [d]])
    ordered = [d for _, _, line in lines for d in sorted(line, key=lambda d: d["bbox"][0])]
    return [{"id": f"{prefix}{i}", **d} for i, d in enumerate(ordered, 1)]
