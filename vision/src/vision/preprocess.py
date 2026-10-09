"""a. 전처리: OpenCV(작은 사진 키우기·노이즈 제거, 대비 보정은 기본 꺼짐), 이후 필요하면 Retinexformer(조도)·UVDoc(곡면)·SIHR(반사)

보정한 이미지에서 찾은 위치는 to_original 행렬로 원본 좌표로 되돌림 (VisionResult의 bbox·polygon은 원본 기준).
"""
import math
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class PreprocessConfig:
    """기본값은 vision/reports/phase2_preprocess.md의 비교에서 고름"""

    min_long_side: int = 1280  # 긴 변이 이보다 작은 사진은 키움 — 운영측 예시(343px)는 키우기 전엔 글자를 거의 못 찾음
    max_upscale: float = 8.0
    denoise: bool = True  # 키우는 사진에만, 키우기 전에 (작은 사진의 압축 잡음이 커지지 않게, 큰 사진은 느려서 생략)
    denoise_h: int = 5
    clahe: bool = False  # 대비 보정 — 비교에서 steel-ocr은 나빠지고(금속 결이 강조돼 b→6) MPSC는 변화 없어 끔
    clahe_clip: float = 2.0


DEFAULT_PREPROCESS = PreprocessConfig()


def preprocess(image: np.ndarray, config: PreprocessConfig = DEFAULT_PREPROCESS) -> tuple[np.ndarray, dict, np.ndarray]:
    """(보정된 이미지, VisionResult.preprocess, to_original) 반환.

    preprocess = {"correction_strength": 0~1, "steps": [{"name", "strength"}, ...]} — 실제로 적용한 보정만, 적용 순서대로.
    to_original: 보정된 이미지 좌표 → 원본 좌표 3×3 행렬 (키우기는 배율, 이후 원근 보정을 넣으면 그 역변환까지 곱함)
    """
    steps: list[dict] = []
    to_original = np.eye(3)
    height, width = image.shape[:2]

    scale = min(config.max_upscale, config.min_long_side / max(height, width))
    if scale > 1:
        if config.denoise:
            denoised = cv2.fastNlMeansDenoisingColored(image, None, config.denoise_h, config.denoise_h, 7, 21)
            steps.append({"name": "denoise", "strength": change_strength(image, denoised)})
            image = denoised
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        steps.append({"name": "upscale", "strength": round(min(1.0, math.log2(scale) / 3), 3)})  # 2배 0.33, 8배 1.0
        to_original = np.diag([1 / scale, 1 / scale, 1.0])

    if config.clahe:
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        lab[..., 0] = cv2.createCLAHE(clipLimit=config.clahe_clip, tileGridSize=(8, 8)).apply(lab[..., 0])
        enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        steps.append({"name": "clahe", "strength": change_strength(image, enhanced)})
        image = enhanced

    # 보정이 여러 개면 원본에서 그만큼 멀어짐: 1 - Π(1 - 각 강도)
    strength = 1 - math.prod(1 - s["strength"] for s in steps)
    return image, {"correction_strength": round(strength, 3), "steps": steps}, to_original


def change_strength(before: np.ndarray, after: np.ndarray, full_change: float = 32.0) -> float:
    """보정이 픽셀을 얼마나 바꿨는지 0~1 — 밝기(0~255)가 평균 full_change 이상 바뀌면 1"""
    diff = np.abs(cv2.cvtColor(after, cv2.COLOR_BGR2GRAY).astype(np.int16) - cv2.cvtColor(before, cv2.COLOR_BGR2GRAY))
    return round(min(1.0, float(diff.mean()) / full_change), 3)


def to_original_coords(detections: list[dict], to_original: np.ndarray, width: int, height: int) -> list[dict]:
    """보정된 이미지에서 찾은 bbox·polygon을 원본 이미지 좌표로 (이미지 밖은 잘라냄)"""
    if np.allclose(to_original, np.eye(3)):
        return detections

    def mapped(points: list[list[float]]) -> list[list[int]]:
        pts = cv2.perspectiveTransform(np.asarray(points, np.float64).reshape(-1, 1, 2), to_original).reshape(-1, 2)
        return [[int(round(min(max(x, 0), width))), int(round(min(max(y, 0), height)))] for x, y in pts]

    out = []
    for d in detections:
        x1, y1, x2, y2 = d["bbox"]
        corners = mapped([[x1, y1], [x2, y1], [x2, y2], [x1, y2]])
        xs, ys = [p[0] for p in corners], [p[1] for p in corners]
        item = {**d, "bbox": [min(xs), min(ys), max(xs), max(ys)]}
        if "polygon" in d:
            item["polygon"] = mapped(d["polygon"])
        out.append(item)
    return out
