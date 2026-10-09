"""c. 기호·그림 인식: YOLOX"""
import numpy as np


def detect_symbols(image: np.ndarray) -> list[dict]:
    """VisionResult.symbols 항목에서 id를 뺀 것의 목록 (id는 recognize가 읽는 순서로 붙임).

    필수: label(워크스페이스 사전의 code, 사전에 없으면 "unknown"), prob(0~1), bbox, source("yolox" | "groundingdino" | "vlm")
    선택: candidates
    """
    # TODO: YOLOX 연결
    return []
