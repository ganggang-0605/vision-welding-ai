"""a. 전처리: OpenCV(대비 보정·노이즈 제거·원근 보정), Retinexformer(조도), UVDoc(곡면), SIHR(반사 제거)"""
import numpy as np


def preprocess(image: np.ndarray) -> tuple[np.ndarray, dict]:
    """(보정된 이미지, VisionResult.preprocess) 반환.

    preprocess = {"correction_strength": 0~1, "steps": [{"name", "strength"}, ...]} — 실제로 적용한 보정만, 적용 순서대로.
    원근·곡면을 펴면 인식 결과 bbox를 원본 좌표로 되돌려야 하므로, 그 변환도 함께 넘길 수 있게 바꿀 것.
    """
    # TODO: CLAHE · 노이즈 제거 · 원근 보정, Retinexformer / UVDoc / SIHR 연동, 보정 강도 계산
    return image, {"correction_strength": 0.0, "steps": []}
