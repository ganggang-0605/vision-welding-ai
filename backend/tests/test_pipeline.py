"""해석 파이프라인 통합 (app/pipeline.py) — 세 단계 패키지 · shared 스키마 · 팀원 API 계약(app/schemas.py)이 맞물리는지"""
import json

import numpy as np
import pytest
from vw_shared import CONFIDENCE_FIELDS, SCHEMAS_DIR, WELDING_CONDITION_FIELDS, load_example, schema_errors, semantic_errors

from app.pipeline import AnalysisError, analyze_image, build_context_input, job_with_analysis, review_analysis
from app.schemas import AssemblyNode, Confidence, Job, ReviewRequest, RobotOutput, SymbolEntry, WeldingCondition, WeldingStandard
from app.store import get_store

IMAGE = np.zeros((1080, 1920, 3), np.uint8)
WELDING = {
    "joint_type": "FILLET", "thickness_mm": 10, "process": "GMAW", "position": "2F",
    "current_a": "420-440", "voltage_v": "35-37", "speed_cm_min": "60", "standard_matched": True, "source": "manual",
}


@pytest.fixture
def job() -> Job:
    return get_store().get_job("demo", "job_demo_p1")  # block_a1 · 연결된 작업 없음 = context_input 예시와 같은 조건


# ── shared 스키마 ↔ 팀원 Pydantic 모델 ──

def test_shared_field_lists_match_api_models():
    assert WELDING_CONDITION_FIELDS == tuple(WeldingCondition.model_fields)
    assert CONFIDENCE_FIELDS == tuple(Confidence.model_fields)


@pytest.mark.parametrize("name, model", [("SymbolEntry", SymbolEntry), ("AssemblyNode", AssemblyNode), ("WeldingStandard", WeldingStandard)])
def test_context_input_defs_match_api_models(name, model):
    schema = json.loads((SCHEMAS_DIR / "context_input.schema.json").read_text(encoding="utf-8"))["$defs"][name]
    assert set(schema["properties"]) == set(schema["required"]) == set(model.model_fields)


@pytest.mark.parametrize("name", ["analysis.example.json", "analysis_revision2.example.json"])
def test_examples_fill_job(name):
    analysis = load_example(name)
    job = Job.model_validate({"id": analysis["job_id"], "workspace_id": analysis["workspace_id"],
                              "project_id": analysis["project_id"], "name": "예시", "status": "draft", "created_at": analysis["created_at"]})
    filled = job_with_analysis(job, analysis)
    if filled.status == "awaiting_approval":  # 승인하면 로봇 JSON 을 만들 수 있어야 함
        RobotOutput.model_validate({**filled.model_dump(), "job_id": filled.id, "approved": True, "approved_by": "검증용"})


# ── 통합 ──

def test_context_input_from_store_matches_example(job):
    context_input = build_context_input(get_store(), job, user_context=None, corrections=[], previous=None)
    assert schema_errors(context_input, "context_input.schema.json") == []
    assert context_input == load_example("context_input.example.json")


def test_analyze_image(job):
    analysis = analyze_image(get_store(), job, IMAGE, "img_0001")
    assert (analysis["revision"], analysis["job_id"], analysis["project_id"]) == (1, job.id, "block_a1")
    filled = job_with_analysis(job, analysis)
    assert filled.status == "needs_review"  # 단계 구현 전: 부재·용접 조건을 못 찾음
    assert filled.needs_review


def test_manual_review_keeps_vision_and_records_corrections(job):
    store = get_store()
    first = analyze_image(store, job, IMAGE, "img_0001")
    review = ReviewRequest(action="manual", values={"part": "A1/L1/M2/S1/P-1", "welding_condition": WELDING})
    second = review_analysis(store, job, first, review)
    assert second["revision"] == 2 and second["vision"] == first["vision"]
    assert {c["target"] for c in second["corrections"]} == {"part", "welding_condition"}
    assert [n for n in second["confidence"]["needs_review"] if n["reason"] == "missing_required"] == []
    filled = job_with_analysis(job, second)
    assert filled.assembly_path == "A1/L1/M2/S1/P-1" and filled.welding_condition.joint_type == "FILLET"


def test_reinterpret_passes_user_context(job):
    store = get_store()
    first = analyze_image(store, job, IMAGE, "img_0001")
    second = review_analysis(store, job, first, ReviewRequest(action="reinterpret", context="8이 아니라 6입니다"))
    assert second["context"]["user_context"] == "8이 아니라 6입니다"
    assert semantic_errors(second) == []


def test_unknown_review_target_is_rejected(job):
    store = get_store()
    first = analyze_image(store, job, IMAGE, "img_0001")
    with pytest.raises(AnalysisError):
        review_analysis(store, job, first, ReviewRequest(action="manual", values={"raw_text": "F/W 6"}))
