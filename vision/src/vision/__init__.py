"""[1단계] 시각 인식 — recognize(image, image_id) → VisionResult (shared/schemas/vision_result.schema.json)"""
from vision.image import load_image
from vision.recognition import recognize

__all__ = ["load_image", "recognize"]
