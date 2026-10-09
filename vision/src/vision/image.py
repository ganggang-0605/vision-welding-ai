"""이미지 읽기"""
import cv2
import numpy as np


def load_image(data: bytes) -> np.ndarray:
    """업로드된 이미지 파일(JPEG·PNG 등) → OpenCV BGR 배열 (H, W, 3)"""
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("이미지를 읽을 수 없습니다")
    return image
