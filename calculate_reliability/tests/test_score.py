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


# ── 1단계가 못 읽고 VLM만 읽은 사진 (PAC 손글씨) ──

def vlm_only_case(consistency, runs, image_attached=True):
    vision = {**REV1["vision"], "texts": [], "symbols": []}
    reading = {"texts": [{"text": "F5.5", "ref_id": "v1"}], "symbols": [{"label": "→", "ref_id": "v2"}]}
    vlm = {**REV1["context"]["vlm"], "reading": reading, "consistency": consistency, "runs": runs, "image_attached": image_attached}
    context = {**REV1["context"], "vlm": vlm, "dictionary_matches": [], "conflicts": []}
    return score(vision, context, [], 80)


@pytest.mark.parametrize("consistency, runs, visual", [(1.0, 3, 90), (0.67, 3, 60), (None, 1, 60)])
def test_vlm_only_reading_scores_by_consistency(consistency, runs, visual):
    """OCR이 못 읽은 표기를 VLM이 읽었다고 시각 점수 0으로 만들지 않음 — VLM 다중 추론 일관성으로 대신 (최대 90)"""
    report = vlm_only_case(consistency, runs)
    assert report["visual"] == visual
    assert report["factors"]["visual"]["ocr_vlm_agreement"] is None
    assert any("VLM만 읽음" in e["message"] for e in report["evidence"] if e["layer"] == "visual")


def test_vlm_without_photo_does_not_count():
    """사진 없이 1단계 결과만 본 VLM이면 시각 근거가 아님 → 0"""
    assert vlm_only_case(1.0, 3, image_attached=False)["visual"] == 0


def test_vlm_only_extra_markings_do_not_lower_agreement():
    """1단계가 읽은 표기는 모두 VLM과 같고 VLM이 표기를 더 읽음 → 일치도 1 (더 읽은 v*는 불일치가 아님)"""
    reading = {**REV1["context"]["vlm"]["reading"]}
    reading["texts"] = reading["texts"] + [{"text": "S-3", "ref_id": "v1"}]
    context = {**REV1["context"], "vlm": {**REV1["context"]["vlm"], "reading": reading}}
    before = run(REV1)["factors"]["visual"]["ocr_vlm_agreement"]
    assert score(REV1["vision"], context, [], 80)["factors"]["visual"]["ocr_vlm_agreement"] == before


def test_arrow_attached_to_text_still_agrees():
    """1단계가 화살표까지 한 줄로 읽은 →F7.5 와 VLM 이 읽은 F7.5 는 같은 표기 (예전엔 일치도 0 → 시각 신뢰도 0)"""
    from calculate_reliability.visual import same_reading

    assert same_reading("→F7.5", "F7.5") and same_reading("p－10 ", "P-10")
    assert not same_reading("P-1O", "P-10")
    vision = {**REV1["vision"], "texts": [{**t, "text": "→" + t["text"]} for t in REV1["vision"]["texts"]]}
    assert score(vision, REV1["context"], [], 80)["factors"]["visual"]["ocr_vlm_agreement"] == \
        run(REV1)["factors"]["visual"]["ocr_vlm_agreement"]
