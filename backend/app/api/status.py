"""해석 파이프라인 연결 상태 — 1·2·3단계 패키지가 실제 모델·API 를 쓸 수 있는지 (GUI 의 '해석 과정'·설정 화면용)

API 키 값은 절대 돌려주지 않고, 채워져 있는지만 알려 준다.
"""
import importlib.util
import os

from db_context_interpreter.vlm import DEFAULT_MODELS
from fastapi import APIRouter
from vision.ocr import DEFAULT_CONFIG as OCR_CONFIG
from vision.ocr import models_available

from app.pipeline import confidence_threshold
from app.schemas import PipelineStatus

router = APIRouter()

# VLM_PROVIDER → (필요한 API 키 환경 변수, SDK 모듈) — db_context_interpreter/vlm/*.py 와 같게
VLM_REQUIREMENTS = {
    "claude": ("ANTHROPIC_API_KEY", "anthropic"),
    "gpt": ("OPENAI_API_KEY", "openai"),
    "gemini": ("GEMINI_API_KEY", "google.genai"),
    "qwen3-vl": (None, "openai"),   # 로컬 OpenAI 호환 서버 (VLM_BASE_URL), 키 없이도 됨
    "internvl": (None, "openai"),
}


def _module_installed(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:  # google 이 없으면 google.genai 를 찾다가 오류
        return False


@router.get("/pipeline/status")
def pipeline_status() -> PipelineStatus:
    """.env 와 설치된 패키지 기준. 키·모델을 바꾸면 백엔드를 다시 켜야 반영된다."""
    provider = os.environ.get("VLM_PROVIDER", "").split("#")[0].strip().lower() or None
    if provider in ("none", "off"):
        provider = None
    key_name, module = VLM_REQUIREMENTS.get(provider, (None, None)) if provider else (None, None)
    return PipelineStatus(
        ocr_available=models_available(),
        ocr_models=OCR_CONFIG.models() if models_available() else {},
        symbol_detector_available=False,  # TODO: 1단계 YOLOX 연결 (vision/symbols.py)
        vlm_provider=provider,
        vlm_model=(os.environ.get("VLM_MODEL") or DEFAULT_MODELS.get(provider)) if provider else None,
        vlm_runs=max(1, int(os.environ.get("VLM_RUNS", 3))),
        vlm_sdk_installed=_module_installed(module) if module else False,
        vlm_api_key_set=bool(os.environ.get(key_name)) if key_name else provider is not None,
        confidence_threshold=confidence_threshold(),
    )
