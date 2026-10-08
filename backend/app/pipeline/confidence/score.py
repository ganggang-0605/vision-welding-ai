"""다계층 신뢰도 산출 (가중치는 조정 예정)"""
from dataclasses import dataclass, field


@dataclass
class ConfidenceReport:
    visual: float = 0.0          # 시각 인식 신뢰도
    db_consistency: float = 0.0  # DB 정합성 신뢰도
    vlm_reasoning: float = 0.0   # VLM 추론 신뢰도
    evidence: list[str] = field(default_factory=list)
    needs_review: list[str] = field(default_factory=list)

    @property
    def overall(self) -> float:
        return min(self.visual, self.db_consistency, self.vlm_reasoning)


def compute_confidence(texts, symbols, context, correction_strength: float) -> ConfidenceReport:
    # TODO: OCR/YOLO 확률 + 전처리 보정 강도 + OCR·VLM 교차 검증 일치 가산
    return ConfidenceReport()
