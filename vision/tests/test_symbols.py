import numpy as np
from vw_shared import schema_errors

import vision.recognition as recognition
from vision import recognize
from vision.symbols import phrase_to_code, to_symbol_detections

PROMPTS = (("handwritten arrow", "→"), ("cross mark", "+"), ("semicircular cutout", "unknown"))


def test_phrase_to_code_matches_partial_phrase():
    """GroundingDINO는 문구 일부만 돌려주기도 함 ("arrow") — 단어가 겹치는 문구의 code, 안 겹치면 None"""
    assert phrase_to_code("arrow", PROMPTS) == "→"
    assert phrase_to_code("Cross Mark", PROMPTS) == "+"
    assert phrase_to_code("cutout", PROMPTS) == "unknown"
    assert phrase_to_code("", PROMPTS) is None
    assert phrase_to_code("steel plate", PROMPTS) is None


def test_to_symbol_detections_clips_and_drops_unmatched():
    """좌표는 정수로 사진 안에 자르고, 어느 문구인지 모르거나 넓이가 없는 상자는 버림"""
    result = to_symbol_detections(
        ["arrow", "", "cross mark", "hole"],
        [0.41234, 0.9, 0.35, 0.5],
        [[-3.2, 10.6, 50.4, 30], [0, 0, 10, 10], [90, 5, 130, 40], [5, 5, 6, 5]],
        PROMPTS, (120, 100),
    )
    assert result == [
        {"label": "→", "prob": 0.4123, "bbox": [0, 11, 50, 30], "source": "groundingdino"},
        {"label": "+", "prob": 0.35, "bbox": [90, 5, 120, 40], "source": "groundingdino"},
    ]


def test_grounding_dino_detections_fit_vision_result(monkeypatch):
    """GroundingDINO 결과를 기호 검출로 끼워도 VisionResult 스키마에 맞음 (사진 크기 120x100, 좌표는 원본 기준)"""
    found = to_symbol_detections(["arrow", "cutout"], [0.4, 0.3], [[0, 11, 50, 30], [60, 50, 110, 90]], PROMPTS, (120, 100))
    monkeypatch.setattr(recognition, "recognize_text", lambda _: [])
    monkeypatch.setattr(recognition, "detect_symbols", lambda _: found)
    result = recognize(np.zeros((100, 120, 3), np.uint8), "img_0001")
    assert [(s["id"], s["label"]) for s in result["symbols"]] == [("s1", "→"), ("s2", "unknown")]
    assert schema_errors(result, "vision_result.schema.json") == []
