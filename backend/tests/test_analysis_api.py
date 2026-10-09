"""사진 올리기 → 1·2·3단계 해석 → 작업자 확인 API (app/pipeline.py 연결)

단계 패키지에 실제 모델이 아직 없어서 해석 결과는 비어 있다 (글자·기호 0개 → 확인 필요).
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
    res = client.post(f"{JOB}/analyze")
    assert res.status_code == 200
    job = res.json()
    assert job["status"] == "needs_review"  # 단계 구현 전: 부재·용접 조건을 못 찾음
    assert job["needs_review"]

    analyses = client.get(f"{JOB}/analyses").json()
    assert len(analyses) == 1
    assert (analyses[0]["image_id"], analyses[0]["revision"], analyses[0]["job_id"]) == (latest["image_id"], 1, "job_demo_p1")
    assert schema_errors(analyses[0], "analysis.schema.json") == []
    assert client.get(JOB).json() == job


def test_analyze_chosen_image(client):
    first = _upload(client).json()
    _upload(client)
    assert client.post(f"{JOB}/analyze", json={"image_id": first["image_id"]}).status_code == 200
    assert client.get(f"{JOB}/analyses").json()[0]["image_id"] == first["image_id"]
    assert client.post(f"{JOB}/analyze", json={"image_id": "img_nope"}).status_code == 404


def test_reanalyze_clears_approval(client):
    path = f"{JOBS}/job_demo_p2"  # 승인된 작업
    _upload(client, path)
    job = client.post(f"{path}/analyze").json()
    assert job["status"] != "approved"
    assert job["approved_at"] is job["approved_by"] is None


def test_review_requires_analysis(client):
    res = client.post(f"{JOB}/review", json={"action": "reinterpret", "context": "6 이 아니라 6.5 입니다"})
    assert res.status_code == 409


def test_review_reinterpret_adds_revision(client):
    _upload(client)
    client.post(f"{JOB}/analyze")
    res = client.post(f"{JOB}/review", json={"action": "reinterpret", "context": "우측은 Slot 입니다"})
    assert res.status_code == 200
    analyses = client.get(f"{JOB}/analyses").json()
    assert [a["revision"] for a in analyses] == [1, 2]
    assert analyses[1]["context"]["user_context"] == "우측은 Slot 입니다"
    assert analyses[1]["vision"] == analyses[0]["vision"]  # 1단계 결과·ID 는 그대로


def test_review_manual(client):
    _upload(client)
    client.post(f"{JOB}/analyze")
    condition = {"joint_type": "FILLET", "process": "GMAW", "position": "2F",
                 "current_a": "420-440", "voltage_v": "35-37", "speed_cm_min": "60"}
    res = client.post(f"{JOB}/review", json={"action": "manual", "values": {
        "interpretation": "3F 용접장 각장 5.5mm",
        "welding_condition": condition,
        "cell": {"left": ["slit"], "right": ["collar_front", "scallop"]},
        "leg_lengths": [{"code": "F", "size_mm": 5.5, "raw_text": "F5.5"}],
    }})
    assert res.status_code == 200
    job = res.json()
    assert job["marking"]["interpretation"] == "3F 용접장 각장 5.5mm"
    assert job["welding_condition"] == condition
    assert job["cell"] == {"left": ["slit"], "right": ["collar_front", "scallop"]}
    assert job["leg_lengths"] == [{"code": "F", "size_mm": 5.5, "raw_text": "F5.5", "meaning": None}]

    revision = client.get(f"{JOB}/analyses").json()[-1]
    corrected = {c["target"]: c["value"] for c in revision["corrections"]}
    assert corrected["welding_condition"] == {**condition, "thickness_mm": None, "standard_matched": True, "source": "manual"}
    assert "cell" not in corrected  # 셀 형태·각장은 아직 Analysis 가 아니라 Job 에만


def test_review_manual_cell_only_keeps_revision(client):
    _upload(client)
    client.post(f"{JOB}/analyze")
    res = client.post(f"{JOB}/review", json={"action": "manual", "values": {"cell": {"left": [], "right": ["slot"]}}})
    assert res.status_code == 200
    assert res.json()["cell"] == {"left": [], "right": ["slot"]}
    assert len(client.get(f"{JOB}/analyses").json()) == 1  # 파이프라인을 다시 돌리지 않음


@pytest.mark.parametrize("values", [
    {"raw_text": "F5.5"},                                  # 고칠 수 없는 대상
    {"interpretation": ""},                                 # 빈 해석
    {"cell": {"left": ["hole"], "right": []}},              # 없는 셀 형태
    {"leg_lengths": [{"code": "F", "size_mm": 0, "raw_text": "F0"}]},  # 각장 0
])
def test_review_manual_invalid(client, values):
    _upload(client)
    client.post(f"{JOB}/analyze")
    assert client.post(f"{JOB}/review", json={"action": "manual", "values": values}).status_code == 422
