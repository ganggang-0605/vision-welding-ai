"""백엔드 → [2단계] 연결: 워크스페이스 사전 · 프로젝트 조립 트리 · 공통 용접 기준과 사진이 2단계 판단에 쓰이는지

1단계 모델이 아직 없어서 recognize 를 shared 예시(P-1 · FW · t=10 · ▲)로 바꿔 끼운다.
"""
import copy
import json

import cv2
import numpy as np
import pytest
from db_context_interpreter import vlm as vlm_module
from db_context_interpreter.vlm import fit_for_vlm
from vw_shared import load_example

import app.pipeline as pipeline

JOB = "/workspaces/demo/jobs/job_demo_p1"  # demo 워크스페이스 · block_a1 프로젝트
VISION = load_example("vision_result.example.json")
VLM_RESPONSE = {
    "interpretation": "부재 P-1, 필렛 용접, 판 두께 10mm, 현장 용접",
    "texts": [{"text": "P-1", "ref_id": "t1", "bbox": None}, {"text": "FW", "ref_id": "t2", "bbox": None},
              {"text": "t=10", "ref_id": "t3", "bbox": None}],
    "symbols": [{"label": "▲", "ref_id": "s1", "bbox": None}],
    "meanings": [{"ref_id": "t3", "meaning": "판 두께 10mm"}],
}


@pytest.fixture(autouse=True)
def example_vision(monkeypatch):
    monkeypatch.delenv("VLM_PROVIDER", raising=False)
    monkeypatch.setattr(pipeline, "recognize", lambda image, image_id: {**copy.deepcopy(VISION), "image_id": image_id})


@pytest.fixture
def fake_vlm(monkeypatch):
    """VLM 을 켜되 실제 API 대신 호출 내용(프롬프트 · 사진)을 기록"""
    calls = []

    def generate(system, prompt, image, model):
        calls.append({"prompt": prompt, "image": image})
        return json.dumps(VLM_RESPONSE, ensure_ascii=False), None

    monkeypatch.setenv("VLM_PROVIDER", "claude")
    monkeypatch.setenv("VLM_RUNS", "1")
    monkeypatch.setitem(vlm_module.PROVIDERS, "claude", generate)
    return calls


def _png() -> bytes:
    ok, encoded = cv2.imencode(".png", np.full((1080, 1920, 3), 128, np.uint8))
    assert ok
    return encoded.tobytes()


def _analyze(client) -> dict:
    assert client.post(f"{JOB}/images", files={"file": ("cell.png", _png(), "image/png")}).status_code == 201
    res = client.post(f"{JOB}/analyze")
    assert res.status_code == 200, res.text
    return res.json()


def _context(client) -> dict:
    return client.get(f"{JOB}/analyses").json()[-1]["context"]


def test_stage2_uses_seed_db(client):
    """사전(FW · ▲) · 조립 트리(P-1) · 용접 기준(FILLET 6~12mm) → 부재 · 용접 조건"""
    job = _analyze(client)
    context = _context(client)
    assert context["part"]["assembly_path"] == "A1/L1/M2/S1/P-1" and context["part"]["found_in_tree"]
    assert {m["code"] for m in context["dictionary_matches"]} >= {"FW", "▲"}
    assert context["welding_condition"]["current_a"] == "420-440"  # FILLET 2F 10mm (data/seed/SOURCES.md)
    assert job["assembly_path"] == "A1/L1/M2/S1/P-1"
    assert job["welding_condition"]["joint_type"] == "FILLET"


def test_stage2_follows_workspace_dictionary(client):
    """워크스페이스 사전에서 FW 를 지우면 이음 형태를 몰라 용접 조건을 판별하지 못함"""
    assert client.delete("/workspaces/demo/symbols/sym_fw").status_code == 204
    _analyze(client)
    context = _context(client)
    t2 = next(m for m in context["dictionary_matches"] if m["ref_ids"] == ["t2"])
    assert t2["code"] is None and t2["match"] != "exact"
    assert context["welding_condition"] is None
    assert "dictionary_unmatched" in [c["type"] for c in context["conflicts"]]


def test_stage2_follows_project_assembly_tree(client, fresh_store):
    """다른 프로젝트(빈 조립 트리)의 작업이면 P-1 이 트리에 없음"""
    project = client.post("/workspaces/demo/projects", json={"name": "빈 블록"}).json()
    job = client.post("/workspaces/demo/jobs", json={"name": "빈 블록 작업", "project_id": project["id"]}).json()
    path = f"/workspaces/demo/jobs/{job['id']}"
    client.post(f"{path}/images", files={"file": ("cell.png", _png(), "image/png")})
    client.post(f"{path}/analyze")
    context = client.get(f"{path}/analyses").json()[-1]["context"]
    assert context["part"]["found_in_tree"] is False and context["part"]["assembly_path"] is None
    assert "part_not_in_tree" in [c["type"] for c in context["conflicts"]]


def test_vlm_gets_uploaded_photo_and_db(client, fake_vlm):
    _analyze(client)
    (call,) = fake_vlm
    # 올린 원본 파일 (긴 변이 1568px 를 넘으면 VLM 한도에 맞게 줄인 JPEG — db_context_interpreter.vlm.fit_for_vlm)
    assert call["image"] == fit_for_vlm(_png(), "image/png")
    assert "A1/L1/M2/S1/P-1" in call["prompt"] and "필렛 용접 (Fillet Weld)" in call["prompt"]
    assert _context(client)["vlm"]["interpretation"] == VLM_RESPONSE["interpretation"]


def test_reinterpret_after_vlm_off_keeps_corrected_v_id(client, fake_vlm, monkeypatch):
    """VLM 만 읽은 표기(v1)를 고친 뒤 VLM 이 꺼지거나 실패해도 재해석이 됨 (이전 VLM 결과를 이어 씀)"""
    VLM_RESPONSE_EXTRA = {**VLM_RESPONSE, "texts": VLM_RESPONSE["texts"] + [{"text": "S-3", "ref_id": "new1", "bbox": None}]}
    monkeypatch.setitem(vlm_module.PROVIDERS, "claude",
                        lambda s, p, i, m: (json.dumps(VLM_RESPONSE_EXTRA, ensure_ascii=False), None))
    _analyze(client)
    assert client.post(f"{JOB}/review", json={"action": "manual", "values": {"v1": "S-3"}}).status_code == 200
    monkeypatch.setenv("VLM_PROVIDER", "off")
    res = client.post(f"{JOB}/review", json={"action": "reinterpret", "context": "VLM 없이 다시"})
    assert res.status_code == 200, res.text
    assert "S-3" in res.json()["marking"]["raw_text"]


def test_review_sends_same_photo_and_user_context(client, fake_vlm):
    _analyze(client)
    res = client.post(f"{JOB}/review", json={"action": "reinterpret", "context": "8이 아니라 6입니다"})
    assert res.status_code == 200, res.text
    assert len(fake_vlm) == 2 and fake_vlm[1]["image"] == fake_vlm[0]["image"]
    assert "8이 아니라 6입니다" in fake_vlm[1]["prompt"]
    assert _context(client)["user_context"] == "8이 아니라 6입니다"
