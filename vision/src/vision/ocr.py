"""b. 문자 인식: PaddleOCR(검출 + 1차 인식), PARSeq(현장 글씨체), TrOCR(손글씨)"""
import numpy as np


def recognize_text(image: np.ndarray) -> list[dict]:
    """VisionResult.texts 항목에서 id를 뺀 것의 목록 (id는 recognize가 읽는 순서로 붙임).

    필수: text, prob(0~1), bbox([x1, y1, x2, y2] 원본 좌표), source("paddleocr" | "parseq" | "trocr")
    선택: polygon, style, char_probs(글자 수와 같은 개수), candidates(확률 낮을 때, 첫 번째 = text)
    """
    # TODO: PaddleOCR 연결 (모델 패키지는 함수 안에서 import — 기본 설치에는 없음)
    return []
