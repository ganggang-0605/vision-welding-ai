"""사진 올리기 → 1·2·3단계 해석 → 작업자 확인 API (app/pipeline.py 연결)

테스트 사진은 표기가 없는 회색 사진이라 해석 결과는 비어 있다 (글자·기호 0개 → 확인 필요).
여기서는 API 가 파이프라인을 부르고 결과를 저장·반영하는 흐름만 점검한다.
"""
import cv2
import numpy as np
import pytest
from vw_shared import schema_errors

JOBS = "/workspaces/demo/jobs"
JOB = f"{JOBS}/job_demo_p1"


def _png(width: int = 640, height: int = 480) -> bytes:
    ok, encoded = cv2.imencode(".png", np.full((height, width, 3), 128, np.uint8))
    assert ok
    return encoded.tobytes()


def _upload(client, path: str = JOB, width: int = 640, height: int = 480):
    return client.post(f"{path}/images", files={"file": ("cell.png", _png(width, height), "image/png")})


def _analyze(client, path: str = JOB, **kwargs) -> dict:
    """해석은 202 로 바로 끝나고 백그라운드에서 돈다 (TestClient 는 백그라운드 작업까지 마치고 돌아옴) → 끝난 작업"""
    res = client.post(f"{path}/analyze", **kwargs)
    assert res.status_code == 202, res.text
    assert res.json()["status"] == "analyzing"
    return client.get(path).json()


def _review(client, body: dict, path: str = JOB) -> dict:
    res = client.post(f"{path}/review", json=body)
    assert res.status_code == 202, res.text
    return client.get(path).json()


def test_upload_and_read_image(client):
    res = _upload(client, width=800, height=600)
    assert res.status_code == 201
    image = res.json()
    assert (image["job_id"], image["filename"], image["content_type"]) == ("job_demo_p1", "cell.png", "image/png")
    assert (image["width"], image["height"]) == (800, 600)
    assert image["image_id"].startswith("img_")

    assert client.get(f"{JOB}/images").json() == [image]
    file = client.get(f"{JOB}/images/{image['image_id']}/file")
    assert file.status_code == 200
    assert file.headers["content-type"] == "image/png"
    assert file.content == _png(800, 600)
    assert client.get(f"{JOB}/images/img_nope/file").status_code == 404
    assert client.get(f"{JOBS}/job_demo_p2/images/{image['image_id']}/file").status_code == 404  # 다른 작업의 사진


def test_upload_rejects_non_image(client):
    res = client.post(f"{JOB}/images", files={"file": ("note.txt", b"not an image", "text/plain")})
    assert res.status_code == 422
    assert client.get(f"{JOB}/images").json() == []


def test_analyze_requires_image(client):
    res = client.post(f"{JOB}/analyze")
    assert res.status_code == 409
    assert "사진" in res.json()["detail"]


def test_analyze_latest_image(client):
    _upload(client)
    latest = _upload(client).json()
    job = _analyze(client)
    assert job["status"] == "needs_review"  # 빈 사진: 표기가 없어 용접 조건을 못 찾음
    assert job["needs_review"] and job["analysis_error"] is None

    analyses = client.get(f"{JOB}/analyses").json()
    assert len(analyses) == 1
    assert (analyses[0]["image_id"], analyses[0]["revision"], analyses[0]["job_id"]) == (latest["image_id"], 1, "job_demo_p1")
    assert schema_errors(analyses[0], "analysis.schema.json") == []


def test_analyze_chosen_image(client):
    first = _upload(client).json()
    _upload(client)
    _analyze(client, json={"image_id": first["image_id"]})
    assert client.get(f"{JOB}/analyses").json()[0]["image_id"] == first["image_id"]
    assert client.post(f"{JOB}/analyze", json={"image_id": "img_nope"}).status_code == 404


def test_analyze_several_images_in_order(client):
    """새 작업에서 여러 장 올리면 모두 순서대로 해석, 작업에는 마지막 사진의 결과"""
    first, second, third = (_upload(client).json() for _ in range(3))
    job = _analyze(client, json={"image_ids": [first["image_id"], third["image_id"], second["image_id"]]})
    assert job["status"] == "needs_review" and job["analysis_stage"] is None
    analyses = client.get(f"{JOB}/analyses").json()
    assert [a["image_id"] for a in analyses] == [first["image_id"], third["image_id"], second["image_id"]]
    res = client.post(f"{JOB}/analyze", json={"image_ids": [first["image_id"], "img_nope"]})
    assert res.status_code == 404 and client.get(JOB).json()["status"] == "needs_review"  # 하나라도 없으면 시작하지 않음


def test_reanalyze_clears_approval(client):
    path = f"{JOBS}/job_demo_p2"  # 승인된 작업
    _upload(client, path)
    job = _analyze(client, path)
    assert job["status"] != "approved"
    assert job["approved_at"] is job["approved_by"] is None


def test_review_requires_analysis(client):
    res = client.post(f"{JOB}/review", json={"action": "reinterpret", "context": "6 이 아니라 6.5 입니다"})
    assert res.status_code == 409
    assert client.get(JOB).json()["status"] == "needs_review"


def test_review_reinterpret_adds_revision(client):
    _upload(client)
    _analyze(client)
    _review(client, {"action": "reinterpret", "context": "우측은 Slot 입니다"})
    analyses = client.get(f"{JOB}/analyses").json()
    assert [a["revision"] for a in analyses] == [1, 2]
    assert analyses[1]["context"]["user_context"] == "우측은 Slot 입니다"
    assert analyses[1]["vision"] == analyses[0]["vision"]  # 1단계 결과·ID 는 그대로


def test_review_manual(client):
    _upload(client)
    _analyze(client)
    condition = {"joint_type": "FILLET", "process": "GMAW", "position": "2F",
                 "current_a": "420-440", "voltage_v": "35-37", "speed_cm_min": "60"}
    job = _review(client, {"action": "manual", "values": {
        "interpretation": "3F 용접장 각장 5.5mm",
        "welding_condition": condition,
        "cell": {"left": ["slit"], "right": ["collar_front", "scallop"]},
        "leg_lengths": [{"code": "F", "size_mm": 5.5, "raw_text": "F5.5"}],
    }})
    assert job["marking"]["interpretation"] == "3F 용접장 각장 5.5mm"
    assert job["welding_condition"] == condition
    assert job["cell"] == {"left": ["slit"], "right": ["collar_front", "scallop"]}
    assert job["leg_lengths"] == [{"code": "F", "size_mm": 5.5, "raw_text": "F5.5", "meaning": "3F 용접장 각장"}]

    revision = client.get(f"{JOB}/analyses").json()[-1]
    corrected = {c["target"]: c["value"] for c in revision["corrections"]}
    assert corrected["welding_condition"] == {**condition, "thickness_mm": None, "standard_matched": True, "source": "manual"}
    assert corrected["cell"] == {"left": ["slit"], "right": ["collar_front", "scallop"]}  # 셀 형태·각장도 2단계 결과로
    assert revision["context"]["leg_lengths"][0]["size_mm"] == 5.5


def test_review_manual_cell_only(client):
    _upload(client)
    _analyze(client)
    job = _review(client, {"action": "manual", "values": {"cell": {"left": [], "right": ["slot"]}}})
    assert job["cell"] == {"left": [], "right": ["slot"]}
    assert [a["revision"] for a in client.get(f"{JOB}/analyses").json()] == [1, 2]


@pytest.mark.parametrize("values", [
    {"raw_text": "F5.5"},                                  # 고칠 수 없는 대상
    {"interpretation": ""},                                 # 빈 해석
    {"cell": {"left": ["hole"], "right": []}},              # 없는 셀 형태
    {"leg_lengths": [{"code": "F", "size_mm": 0, "raw_text": "F0"}]},  # 각장 0
    {"t9": "FW"},                                           # 이전 해석에 없는 표기
    {},                                                     # 바꾼 값 없음
])
def test_review_manual_invalid(client, values):
    """고친 값은 백그라운드로 넘기기 전에 확인해 바로 422 (해석은 시작하지 않음)"""
    _upload(client)
    before = _analyze(client)
    assert client.post(f"{JOB}/review", json={"action": "manual", "values": values}).status_code == 422
    assert client.get(JOB).json() == before


# ── 백그라운드 해석 ──

def test_analyze_twice_while_running_conflicts(client, fresh_store):
    _upload(client)
    fresh_store.start_analysis("demo", "job_demo_p1")  # 다른 요청이 해석 중
    res = client.post(f"{JOB}/analyze")
    assert res.status_code == 409 and "해석 중" in res.json()["detail"]


def test_failed_analysis_restores_status_and_explains(client, monkeypatch):
    import app.api.jobs as jobs_api

    def broken(*args):
        raise RuntimeError("OCR 모델을 불러오지 못함")

    monkeypatch.setattr(jobs_api, "analyze_image", broken)
    before = client.get(JOB).json()
    _upload(client)
    job = _analyze(client)
    assert job["status"] == before["status"] == "needs_review"
    assert "OCR 모델을 불러오지 못함" in job["analysis_error"]
    assert client.get(f"{JOB}/analyses").json() == []


def test_analysis_reports_stages(client, fresh_store, monkeypatch):
    """해석 중에는 지금 단계(analysis_stage)가 1 → 2 → 3단계로 바뀌고(진행 표시), 끝나면 비어 있음"""
    stages = []
    set_stage = fresh_store.set_analysis_stage

    def record(workspace_id, job_id, stage):
        set_stage(workspace_id, job_id, stage)
        job = fresh_store.get_job(workspace_id, job_id)
        stages.append((job.analysis_stage, job.analysis_stage_at is not None))

    monkeypatch.setattr(fresh_store, "set_analysis_stage", record)
    _upload(client)
    res = client.post(f"{JOB}/analyze")
    assert (res.json()["analysis_stage"], res.json()["analysis_stage_at"] is not None) == ("vision", True)
    assert stages == [("vision", True), ("context", True), ("confidence", True)]
    job = client.get(JOB).json()
    assert job["analysis_stage"] is job["analysis_stage_at"] is None

    stages.clear()
    res = client.post(f"{JOB}/review", json={"action": "reinterpret", "context": "다시"})
    assert res.json()["analysis_stage"] == "context"  # 작업자 확인은 2단계부터
    assert [stage for stage, _ in stages] == ["context", "confidence"]


def test_failed_analysis_clears_stage(client, monkeypatch):
    import app.api.jobs as jobs_api

    def broken(*args):
        raise RuntimeError("실패")

    monkeypatch.setattr(jobs_api, "analyze_image", broken)
    _upload(client)
    job = _analyze(client)
    assert job["analysis_stage"] is job["analysis_stage_at"] is None


def test_approve_blocked_while_analyzing(client, fresh_store):
    fresh_store.start_analysis("demo", "job_demo_p3")
    res = client.post(f"{JOBS}/job_demo_p3/approve", json={"approved_by": "김용접"})
    assert res.status_code == 409


# ── 1단계가 보정한 사진 ──

def test_small_photo_preprocessed_for_screen(client):
    """작은 사진(긴 변 1280px 미만)은 1단계가 키운 사진(OCR 이 본 사진)을 저장해 화면에서 보여 줌"""
    image = _upload(client, width=343, height=200).json()
    assert client.get(f"{JOB}/images/{image['image_id']}/preprocessed").status_code == 404  # 해석 전
    _analyze(client)
    (stored,) = client.get(f"{JOB}/images").json()
    assert stored["preprocessed"] is True
    res = client.get(f"{JOB}/images/{image['image_id']}/preprocessed")
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    assert cv2.imdecode(np.frombuffer(res.content, np.uint8), cv2.IMREAD_COLOR).shape[:2] == (746, 1280)


def test_large_photo_not_preprocessed(client):
    image = _upload(client, width=1920, height=1080).json()
    _analyze(client)
    assert client.get(f"{JOB}/images").json()[0]["preprocessed"] is False
    assert client.get(f"{JOB}/images/{image['image_id']}/preprocessed").status_code == 404


# ── 작업 생성 때 적은 조립 경로 (PAC 셀 사진엔 부재 번호가 없음) ──

def test_analyze_uses_assembly_path_from_job(client):
    """사진에 부재 번호가 없으면 2단계가 작업에 적은 조립 경로를 씀 → '부재를 못 찾음' 확인 항목이 없음"""
    job = client.post(JOBS, json={"name": "셀 사진", "project_id": "block_a1", "assembly_path": "A1/L1/M2/S1/P-2"}).json()
    path = f"{JOBS}/{job['id']}"
    _upload(client, path)
    analyzed = _analyze(client, path)
    assert analyzed["assembly_path"] == "A1/L1/M2/S1/P-2"
    assert analyzed["needs_review"]  # 용접 조건은 여전히 확인 필요
    assert not any("부재" in message for message in analyzed["needs_review"])

    part = client.get(f"{path}/analyses").json()[-1]["context"]["part"]
    assert (part["assembly_path"], part["found_in_tree"], part["ref_ids"]) == ("A1/L1/M2/S1/P-2", True, [])

    reviewed = _review(client, {"action": "reinterpret", "context": "셀 사진"}, path)
    assert reviewed["assembly_path"] == "A1/L1/M2/S1/P-2"  # 다시 해석해도 유지


def test_analyze_without_assembly_path(client):
    job = client.post(JOBS, json={"name": "경로 없음", "project_id": "block_a1"}).json()
    path = f"{JOBS}/{job['id']}"
    _upload(client, path)
    analyzed = _analyze(client, path)
    assert analyzed["assembly_path"] is None
    assert any("부재" in message for message in analyzed["needs_review"])
