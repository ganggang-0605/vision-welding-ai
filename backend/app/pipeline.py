"""표기 정보 해석 파이프라인 통합: [1단계] vision → [2단계] db_context_interpreter → [3단계] calculate_reliability

각 단계는 저장소 루트의 같은 이름 폴더에 있는 독립 패키지이고, 여기서는 DB 조회 · 호출 순서 · Analysis 조립만 한다.
단계 사이 데이터 형식은 shared/schemas (Analysis = analysis.schema.json).
api/jobs.py 의 analyze·review 가 호출한다 (사진·Analysis 는 지금 store 메모리에 저장).
"""
import os
import threading
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

import cv2
import numpy as np
from calculate_reliability import score
from db_context_interpreter import interpret
from vision import recognize
from vision.preprocess import preprocess
from vw_shared import is_ref, schema_errors, semantic_errors, to_job_fields

from app.schemas import AnalysisStage, Job, ReviewRequest, WeldingStandard
from app.store import Store, new_id

SCHEMA_VERSION = "1.1"
# 단계가 바뀔 때 부르는 함수 (api/jobs.py 가 작업의 analysis_stage 에 남겨 GUI 진행 표시에 씀)
OnStage = Callable[[AnalysisStage], None]


def _no_stage(stage: AnalysisStage) -> None:
    pass


class AnalysisError(ValueError):
    """파이프라인 결과가 shared 스키마·단계 사이 규칙에 맞지 않음 (작업자 입력이 잘못됐거나 단계 구현 오류)"""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def confidence_threshold() -> float:
    """.env 의 CONFIDENCE_THRESHOLD (0~100)"""
    return float(os.environ.get("CONFIDENCE_THRESHOLD", 80))


def analyze_image(store: Store, job: Job, image: np.ndarray, image_id: str, on_stage: OnStage = _no_stage) -> dict:
    """새 사진 해석 (revision 1) → Analysis. 1단계 전처리(작은 사진 키우기 · 노이즈 제거)를 거친 사진은 저장해 두고
    화면(GET .../images/{image_id}/preprocessed)에서 OCR 이 본 사진으로 보여 준다"""
    on_stage("vision")
    vision = recognize(image, image_id)
    keep_preprocessed(store, job, image_id, image)
    return _interpret(store, job, vision, revision=1, user_context=None, corrections=[], previous=None, image=image,
                      on_stage=on_stage)


def keep_preprocessed(store: Store, job: Job, image_id: str, image: np.ndarray) -> None:
    """1단계와 같은 전처리를 한 사진 (보정한 게 없으면 저장하지 않음 — 원본을 그대로 씀)"""
    clean, prep, _ = preprocess(image)
    if not prep["steps"] or store.get_image(job.id, image_id) is None:
        return
    ok, encoded = cv2.imencode(".png", clean)
    if ok:
        store.set_preprocessed(job.id, image_id, encoded.tobytes())


def review_analysis(store: Store, job: Job, previous: dict, review: ReviewRequest, on_stage: OnStage = _no_stage) -> dict:
    """작업자 확인 → 1단계 결과와 ID는 그대로 두고 2단계부터 다시 해석 (revision + 1) → Analysis

    reinterpret: context 를 맥락으로 추가 / manual: values 를 작업자 수정(corrections)으로 추가
    """
    user_context = previous["context"].get("user_context")
    corrections = list(previous.get("corrections", []))
    if review.action == "reinterpret":
        user_context = review.context
    else:
        corrections = merge_corrections(corrections, (review.values or {}).items(), previous)
    return _interpret(store, job, previous["vision"], revision=previous["revision"] + 1,
                      user_context=user_context, corrections=corrections, previous=previous, on_stage=on_stage)


def job_with_analysis(job: Job, analysis: dict) -> Job:
    """Analysis 를 반영한 Job (status · assembly_path · marking · welding_condition · cell · leg_lengths · confidence ·
    evidence · needs_review). 저장은 호출한 쪽에서 store.save_job"""
    return Job.model_validate({**job.model_dump(), **to_job_fields(analysis),
                               "analysis_error": None, "analysis_stage": None, "analysis_stage_at": None})


def build_context_input(
    store: Store, job: Job, *, user_context: str | None, corrections: list[dict], previous: dict | None,
) -> dict:
    """2단계 입력 (shared/schemas/context_input.schema.json) — 2단계는 DB 를 직접 읽지 않고 이것만 쓴다"""
    related = [store.get_job(job.workspace_id, job_id) for job_id in job.related_job_ids]
    vlm = previous["context"]["vlm"] if previous else None
    return {
        "workspace_id": job.workspace_id,
        "project_id": job.project_id,
        "job_assembly_path": job.assembly_path,
        "symbols": [s.model_dump(mode="json") for s in store.list_symbols(job.workspace_id)],
        "assembly_tree": [n.model_dump(mode="json") for n in store.get_assembly_tree(job.workspace_id, job.project_id)],
        "welding_standards": [w.model_dump(mode="json") for w in store.welding_standards],
        "user_context": user_context,
        "corrections": corrections,
        "previous_reading": vlm["reading"] if vlm else None,
        "related_jobs": [
            {"job_id": r.id, "assembly_path": r.assembly_path, "interpretation": r.marking.interpretation if r.marking else None}
            for r in related if r is not None
        ],
    }


def manual_welding_condition(value: dict, standards: list[WeldingStandard]) -> dict:
    """GUI 가 보낸 Job 모양 용접 조건(6개 필드) → Correction 의 2단계 WeldingCondition (source=manual).
    standard_matched 는 공통 표준 용접 기준의 한 행과 6개 값이 모두 같은지로 정한다 (판 두께는 모름)."""
    fields = ("joint_type", "process", "position", "current_a", "voltage_v", "speed_cm_min")
    condition = {key: value.get(key) for key in fields}
    matched = any(all(getattr(row, key) == condition[key] for key in fields) for row in standards)
    return {**condition, "thickness_mm": value.get("thickness_mm"), "standard_matched": matched, "source": "manual"}


def merge_corrections(existing: list[dict], values: Iterable[tuple[str, object]], previous: dict) -> list[dict]:
    """ReviewRequest(manual).values → Analysis.corrections. 같은 대상을 다시 고치면 새 값으로 바꾼다.

    값은 그대로(예: {"t2": "FW"}) 또는 의미까지 {"t3": {"value": "t=10", "meaning": "판 두께 10mm"}}.
    welding_condition · cell · leg_lengths 의 값은 객체·목록 그대로.
    """
    merged = {c["target"]: c for c in existing}
    for target, raw in values:
        correction = {"target": target}
        if isinstance(raw, dict) and is_ref(target):
            correction |= raw
        else:
            correction["value"] = raw
        before = current_value(previous, target)
        if before is not None:
            correction["previous"] = before
        merged[target] = correction
    return list(merged.values())


def current_value(analysis: dict, target: str):
    """작업자가 고치기 전 값 (Correction.previous 기록용)"""
    fixed = {c["target"]: c["value"] for c in analysis.get("corrections", [])}
    if target in fixed:
        return fixed[target]
    vision, context = analysis["vision"], analysis["context"]
    if is_ref(target):
        reading = context["vlm"]["reading"]["texts"] + context["vlm"]["reading"]["symbols"] if context["vlm"] else []
        found = {d["id"]: d.get("text") or d.get("label") for d in vision["texts"] + vision["symbols"]}
        found |= {x["ref_id"]: x.get("text") or x.get("label") for x in reading if x["ref_id"][0] == "v"}
        return found.get(target)
    cell = context.get("cell")
    return {
        "part": context["part"]["assembly_path"],
        "welding_condition": context["welding_condition"],
        "interpretation": context["vlm"]["interpretation"] if context["vlm"] else None,
        "cell": {"left": cell["left"], "right": cell["right"]} if cell else None,
        "leg_lengths": [{k: leg[k] for k in ("code", "size_mm", "raw_text")} for leg in context.get("leg_lengths", [])] or None,
    }.get(target)


def stage2_image(store: Store, job: Job, image_id: str, fallback: np.ndarray | None = None) -> bytes | np.ndarray | None:
    """2단계 VLM 에 보여 줄 사진 — 올린 원본 파일 그대로 (작업자 확인 때도 같은 사진). 저장된 게 없으면 fallback.
    1단계 보정본은 쓰지 않는다: 노이즈 제거가 작은 사진의 흐린 마커 획을 지워 VLM 이 글자를 못 읽음 (PAC 손글씨 예시 2).
    작은 사진은 2단계가 노이즈 제거 없이 키워서 보낸다 (db_context_interpreter.vlm.fit_for_vlm)"""
    found = store.get_image(job.id, image_id)
    return found[1] if found else fallback


# 최근 VLM 호출 실패 (GET /pipeline/status 가 보여 줌 — .env 의 키·모델 문제를 설정 화면에서 바로 알 수 있게)
_vlm_state = {"error": None, "at": None}
_vlm_lock = threading.Lock()


def last_vlm_error() -> tuple[str | None, datetime | None]:
    with _vlm_lock:
        return _vlm_state["error"], _vlm_state["at"]


def _record_vlm(context: dict) -> None:
    """VLM 이 실패하면 기록, 성공하면 지움 (VLM 을 끈 해석은 그대로 둠)"""
    with _vlm_lock:
        if context.get("vlm_error"):
            _vlm_state.update(error=context["vlm_error"], at=datetime.now(UTC))
        elif context["vlm"] is not None:
            _vlm_state.update(error=None, at=None)


def _interpret(
    store: Store, job: Job, vision: dict, *, revision: int,
    user_context: str | None, corrections: list[dict], previous: dict | None, image: np.ndarray | None = None,
    on_stage: OnStage = _no_stage,
) -> dict:
    on_stage("context")
    context_input = build_context_input(store, job, user_context=user_context, corrections=corrections, previous=previous)
    context = interpret(vision, context_input, image=stage2_image(store, job, vision["image_id"], image),
                        previous_vlm=previous["context"]["vlm"] if previous else None)
    _record_vlm(context)
    on_stage("confidence")
    confidence = score(vision, context, corrections, confidence_threshold())
    analysis = {
        "schema_version": SCHEMA_VERSION,
        "analysis_id": new_id("an"),
        "workspace_id": job.workspace_id,
        "project_id": job.project_id,
        "job_id": job.id,
        "image_id": vision["image_id"],
        "revision": revision,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "vision": vision,
        "context": context,
        "confidence": confidence,
    }
    if corrections:
        analysis["corrections"] = corrections
    errors = schema_errors(analysis, "analysis.schema.json") or semantic_errors(analysis)
    if errors:
        raise AnalysisError(errors)
    return analysis
