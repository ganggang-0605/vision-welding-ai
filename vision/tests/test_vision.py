import cv2
import numpy as np
import pytest
from vw_shared import schema_errors

import vision.recognition as recognition
from vision import load_image, recognize


@pytest.fixture
def image() -> np.ndarray:
    return np.zeros((1080, 1920, 3), np.uint8)


def test_output_matches_schema(image):
    result = recognize(image, "img_0001")
    assert schema_errors(result, "vision_result.schema.json") == []
    assert result["image_size"] == {"width": 1920, "height": 1080}


def test_ids_follow_reading_order(image, monkeypatch):
    """같은 줄은 왼→오른, 줄은 위→아래 (shared/examples/vision_result.example.json과 같은 배치)"""
    found = [
        {"text": "t=10", "prob": 0.91, "bbox": [420, 390, 560, 440], "source": "paddleocr"},
        {"text": "FW", "prob": 0.62, "bbox": [640, 300, 742, 360], "source": "trocr"},
        {"text": "P-1", "prob": 0.97, "bbox": [412, 288, 598, 362], "source": "paddleocr"},
    ]
    monkeypatch.setattr(recognition, "recognize_text", lambda _: found)
    result = recognize(image, "img_0001")
    assert [(t["id"], t["text"]) for t in result["texts"]] == [("t1", "P-1"), ("t2", "FW"), ("t3", "t=10")]
    assert schema_errors(result, "vision_result.schema.json") == []


def test_load_image_roundtrip(image):
    ok, encoded = cv2.imencode(".png", image)
    assert ok and load_image(encoded.tobytes()).shape == image.shape
    with pytest.raises(ValueError):
        load_image(b"not an image")
