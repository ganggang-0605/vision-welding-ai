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


# ── 점수 계산 (shared 예시의 점수가 그대로 나와야 함) ──

@pytest.mark.parametrize("analysis", [REV1, REV2], ids=["revision1", "revision2"])
def test_scores_match_examples(analysis):
    report = run(analysis)
    expected = analysis["confidence"]
    assert {k: report[k] for k in ("visual", "db_consistency", "vlm_reasoning", "overall", "passed")} == {
        k: expected[k] for k in ("visual", "db_consistency", "vlm_reasoning", "overall", "passed")}


def test_low_confidence_marking_needs_review():
    """revision 1: 손글씨 FW 62% → 확인 필요 (후보 FW · EW). revision 2에서 작업자가 확인하면 빠짐"""
    assert [(n["target"], n["reason"], n.get("candidates")) for n in run(REV1)["needs_review"]] == [
        ("t2", "low_visual_confidence", ["FW", "EW"])]
    assert run(REV2)["needs_review"] == []


def test_evidence_explains_each_layer():
    layers = {e["layer"] for e in run(REV1)["evidence"]}
    assert layers == {"visual", "db_consistency", "vlm_reasoning"}


def test_vlm_off_is_left_out_of_overall():
    """VLM을 끄면 VLM 추론 신뢰도는 판단에서 빼고(100) 나머지 둘로 정함"""
    context = {**REV2["context"], "vlm": None}
    report = score(REV2["vision"], context, REV2["corrections"], 80)
    assert report["vlm_reasoning"] == 100 and report["overall"] == min(report["visual"], report["db_consistency"])


def test_vlm_failure_blocks_and_explains():
    context = {**REV2["context"], "vlm": None, "vlm_error": "claude(claude-opus-5-5) 추론 3번 모두 실패 — 인증 오류"}
    report = score(REV2["vision"], context, REV2["corrections"], 80)
    assert report["vlm_reasoning"] == 0 and report["passed"] is False
    assert ("interpretation", "vlm_failed") in [(n["target"], n["reason"]) for n in report["needs_review"]]
    assert semantic_errors({**REV2, "context": context, "confidence": report}) == []


def test_single_run_without_token_prob_needs_review():
    """Claude 1회 추론은 일관성을 잴 수 없어 60 (VLM_RUNS ≥ 2 권장)"""
    vlm = {**REV2["context"]["vlm"], "consistency": None, "runs": 1}
    report = score(REV2["vision"], {**REV2["context"], "vlm": vlm}, REV2["corrections"], 80)
    assert report["vlm_reasoning"] == 60 and report["passed"] is False


def test_nothing_read_scores_zero():
    vision = {**REV1["vision"], "texts": [], "symbols": []}
    context = {**REV1["context"], "dictionary_matches": [], "conflicts": [], "vlm": None,
               "part": {"node_id": None, "assembly_path": None, "level": None, "found_in_tree": False, "ref_ids": []},
               "welding_condition": None}
    report = score(vision, context, [], 80)
    assert report["visual"] == 0 and report["factors"]["visual"]["recognition_prob"] is None
    assert [n["target"] for n in report["needs_review"]] == ["part", "welding_condition"]


def test_warning_conflicts_become_review_items():
    conflict = {"type": "ocr_vlm_mismatch", "severity": "warning", "message": "1단계는 'FW', VLM은 'EW'로 읽음", "ref_ids": ["t2"]}
    info = {"type": "ocr_vlm_mismatch", "severity": "info", "message": "참고", "ref_ids": ["t3"]}
    context = {**REV1["context"], "conflicts": [info, conflict]}
    report = score(REV1["vision"], context, [], 80)
    assert [(n["target"], n["reason"]) for n in report["needs_review"]] == [("t2", "ocr_vlm_mismatch")]  # t2 하나만 (중복 없음)


def test_standard_conflict_targets_welding_condition_and_lowers_db_score():
    conflict = {"type": "standard_conflict", "severity": "warning", "message": "각장 5.5mm 기준이 없어 …", "ref_ids": ["t2"]}
    report = score(REV2["vision"], {**REV2["context"], "conflicts": [conflict]}, REV2["corrections"], 80)
    assert report["db_consistency"] == 72  # 92 − 20
    assert ("welding_condition", "standard_conflict") in [(n["target"], n["reason"]) for n in report["needs_review"]]
