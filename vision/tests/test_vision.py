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


def test_to_text_detections_converts_paddleocr_result():
    """PaddleOCR 결과(꼭짓점 4개, 실수 좌표) → bbox·polygon 정수 좌표, 빈 글자 제외 (id는 recognize가 붙임)"""
    from vision.ocr import to_text_detections

    polys = [[[412.4, 288.6], [598, 288.6], [598, 362], [412.4, 362]], [[0, 0], [5, 0], [5, 5], [0, 5]]]
    result = to_text_detections(["P-1", " "], [0.97123, 0.5], polys)

    assert result == [{
        "text": "P-1", "prob": 0.9712, "bbox": [412, 289, 598, 362],
        "polygon": [[412, 289], [598, 289], [598, 362], [412, 362]], "source": "paddleocr",
    }]


def test_preprocess_upscales_small_image_and_maps_back():
    """작은 사진은 긴 변 1280px로 키우고(노이즈 제거 → 키우기), 찾은 위치는 원본 좌표로 되돌림"""
    from vision.preprocess import preprocess, to_original_coords

    small = np.full((240, 320, 3), 128, np.uint8)
    clean, prep, to_original = preprocess(small)

    assert clean.shape[:2] == (960, 1280)
    assert [s["name"] for s in prep["steps"]] == ["denoise", "upscale"]
    assert 0 < prep["correction_strength"] <= 1
    found = [{"text": "F5.5", "bbox": [400, 400, 800, 600], "polygon": [[400, 400], [800, 400], [800, 600], [400, 600]]}]
    mapped = to_original_coords(found, to_original, 320, 240)
    assert mapped[0]["bbox"] == [100, 100, 200, 150]
    assert mapped[0]["polygon"][2] == [200, 150]


def test_preprocess_keeps_large_image_size(image):
    from vision.preprocess import preprocess

    clean, prep, to_original = preprocess(image)  # 1920×1080: 키우지 않음
    assert clean.shape == image.shape
    assert prep == {"correction_strength": 0, "steps": []}
    assert np.allclose(to_original, np.eye(3))


def test_zoom_crop_maps_bbox_into_crop():
    """확대 재판독: bbox 주변을 여백과 함께 잘라내고, 원래 bbox를 잘린 이미지 좌표로 돌려줌"""
    from vision.ocr import zoom_crop

    image = np.zeros((1000, 2000, 3), np.uint8)
    crop, inner = zoom_crop(image, [100, 100, 300, 200], margin=0.5, max_side=10000)
    assert crop.shape[:2] == (200, 400)
    assert inner == [100, 50, 300, 150]
    assert zoom_crop(image, [0, 0, 3, 3], margin=0.1, max_side=960) is None


def test_pick_reread_replaces_text_only_when_more_confident():
    from vision.ocr import pick_reread

    original = {"text": "B1S630N", "prob": 0.7, "bbox": [0, 0, 10, 10], "source": "paddleocr"}
    better = pick_reread(original, [{"text": "B1Sb", "prob": 0.9}, {"text": "30N", "prob": 0.8}])
    assert better == {**original, "text": "B1Sb30N", "prob": round((0.9 * 4 + 0.8 * 3) / 7, 4)}
    assert pick_reread(original, [{"text": "B1S", "prob": 0.5}]) is original
    assert pick_reread(original, []) is original


def test_warm_up_without_models(monkeypatch):
    """모델 패키지가 없으면(CI) 미리 불러오기를 건너뜀"""
    from vision import ocr

    monkeypatch.setattr(ocr, "models_available", lambda: False)
    assert ocr.warm_up() is False
