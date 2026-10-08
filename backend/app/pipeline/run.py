"""표기 정보 해석 파이프라인: 시각 인식 → DB 기반 맥락 해석 → 신뢰도 산출"""
from app.pipeline.confidence.score import ConfidenceReport, compute_confidence
from app.pipeline.context.interpret import interpret_context
from app.pipeline.preprocess.denoise import preprocess
from app.pipeline.recognition.ocr import recognize_text
from app.pipeline.recognition.symbols import detect_symbols


def run_pipeline(image, workspace_id: str) -> dict:
    # [1단계] 시각 인식
    clean, correction_strength = preprocess(image)
    texts = recognize_text(clean)
    symbols = detect_symbols(clean)

    # [2단계] DB 기반 맥락 해석 (용접 기준 / 문자·기호 / 조립 경로 + VLM)
    context = interpret_context(clean, texts, symbols, workspace_id)

    # [3단계] 신뢰도 산출 및 판단 근거
    confidence: ConfidenceReport = compute_confidence(texts, symbols, context, correction_strength)

    return {"texts": texts, "symbols": symbols, "context": context, "confidence": confidence}
