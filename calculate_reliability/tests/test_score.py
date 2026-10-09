import pytest
from vw_shared import load_example, schema_errors, semantic_errors

from calculate_reliability import score

REV1 = load_example("analysis.example.json")
REV2 = load_example("analysis_revision2.example.json")


def run(analysis: dict) -> dict:
    return score(analysis["vision"], analysis["context"], analysis.get("corrections", []), 80)


@pytest.mark.parametrize("analysis", [REV1, REV2], ids=["revision1", "revision2"])
def test_output_matches_schema_and_rules(analysis):
    report = run(analysis)
    assert schema_errors(report, "confidence_report.schema.json") == []
    assert semantic_errors({**analysis, "confidence": report}) == []


@pytest.mark.parametrize("analysis", [REV1, REV2], ids=["revision1", "revision2"])
def test_factors_match_examples(analysis):
    """근거 값은 스키마 설명대로 계산 → 예시의 factors와 같아야 함 (revision 2는 작업자가 확인한 t2를 뺌)"""
    assert run(analysis)["factors"] == analysis["confidence"]["factors"]


def test_missing_welding_condition_needs_review():
    context = {**REV1["context"], "welding_condition": None}
    report = score(REV1["vision"], context, [], 0)
    assert report["passed"] is False  # 기준치 0이어도 필수 값이 없으면 통과 못 함
    assert [(n["target"], n["reason"]) for n in report["needs_review"]] == [("welding_condition", "missing_required")]
    assert semantic_errors({**REV1, "context": context, "confidence": report}) == []
