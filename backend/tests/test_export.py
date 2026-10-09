import json
from datetime import datetime
from pathlib import Path

import pytest

from app.export.robot_json import to_robot_json
from app.main import app
from app.schemas import Confidence, Job, Marking, RobotOutput, WeldingCondition

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "schemas" / "robot_output.schema.json").read_text(encoding="utf-8")
)
JOBS = "/workspaces/demo/jobs"

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "number": (int, float)}


def check_schema(value, schema: dict, path: str = "$") -> None:
    """jsonschema 없이 쓰는 최소 검사 (type · required · properties · items · minimum/maximum · date-time)"""
    if "type" in schema:
        expected = schema["type"]
        assert isinstance(value, _TYPES[expected]), f"{path}: {expected} 가 아님"
        assert not (expected == "number" and isinstance(value, bool)), f"{path}: number 가 아님"
    for key in schema.get("required", []):
        assert key in value, f"{path}.{key} 누락"
    for key, sub in schema.get("properties", {}).items():
        if key in value:
            check_schema(value[key], sub, f"{path}.{key}")
    for i, item in enumerate(value if "items" in schema else []):
        check_schema(item, schema["items"], f"{path}[{i}]")
    if "minimum" in schema:
        assert value >= schema["minimum"], path
    if "maximum" in schema:
        assert value <= schema["maximum"], path
    if schema.get("format") == "date-time":
        assert datetime.fromisoformat(value).tzinfo is not None, f"{path}: 시간대 없는 date-time"


def assert_robot_output(body: dict) -> None:
    check_schema(body, SCHEMA)
    assert set(body) <= set(SCHEMA["properties"])
    try:
        import jsonschema
    except ImportError:  # requirements 에 없음 — 설치돼 있을 때만 정식 검증
        return
    jsonschema.validate(body, SCHEMA)


def test_schema_requires_workspace_and_project_id():
    assert {"workspace_id", "project_id"} <= set(SCHEMA["required"])


def test_schema_matches_robot_output_model():
    """JSON 스키마 파일 · RobotOutput 모델 · OpenAPI 응답 스키마가 같은 모양이다 (중첩 객체까지 모든 필드 필수)."""
    openapi = app.openapi()["components"]["schemas"]
    nested = {"marking": Marking, "welding_condition": WeldingCondition, "confidence": Confidence}
    for schema, model in [(SCHEMA, RobotOutput), *((SCHEMA["properties"][key], m) for key, m in nested.items())]:
        fields = set(model.model_fields)
        assert set(schema["properties"]) == set(schema["required"]) == fields, model.__name__
        assert set(openapi[model.__name__]["required"]) == fields, model.__name__


def test_export_approved_job(client):
    res = client.get(f"{JOBS}/job_demo_p2/export")
    assert res.status_code == 200
    body = res.json()
    assert_robot_output(body)
    job = client.get(f"{JOBS}/job_demo_p2").json()
    assert body == {
        "job_id": "job_demo_p2",
        "workspace_id": "demo",
        "project_id": "hull_3201",
        "created_at": job["created_at"],
        "assembly_path": "A1/L1/M2/S1/P-2",
        "marking": job["marking"],
        "welding_condition": job["welding_condition"],
        "confidence": job["confidence"],
        "evidence": job["evidence"],
        "needs_review": [],
        "approved": True,
        "approved_by": "[작업자]",
    }


def test_check_schema_detects_violations(client):
    body = client.get(f"{JOBS}/job_demo_p2/export").json()
    with pytest.raises(AssertionError, match="workspace_id"):
        check_schema({k: v for k, v in body.items() if k != "workspace_id"}, SCHEMA)
    with pytest.raises(AssertionError, match="project_id"):
        check_schema({k: v for k, v in body.items() if k != "project_id"}, SCHEMA)
    with pytest.raises(AssertionError, match="overall"):
        check_schema({**body, "confidence": {**body["confidence"], "overall": 101}}, SCHEMA)


@pytest.mark.parametrize("job_id", ["job_demo_p1", "job_demo_p3"])
def test_export_requires_approval(client, job_id):
    res = client.get(f"{JOBS}/{job_id}/export")
    assert res.status_code == 409
    assert "승인" in res.json()["detail"]


def test_export_draft_conflict(client):
    job = client.post(JOBS, json={"name": "초안", "project_id": "hull_3201"}).json()
    assert client.get(f"{JOBS}/{job['id']}/export").status_code == 409


def test_export_after_approve(client):
    client.post(f"{JOBS}/job_demo_p3/approve", json={"approved_by": "김용접"})
    res = client.get(f"{JOBS}/job_demo_p3/export")
    assert res.status_code == 200
    body = res.json()
    assert_robot_output(body)
    assert (body["approved"], body["approved_by"]) == (True, "김용접")
    assert body["project_id"] == "hull_3201"
    assert body["welding_condition"]["joint_type"] == "BUTT_V"


def test_to_robot_json_rejects_incomplete_job():
    job = Job(id="job_x", workspace_id="demo", project_id="hull_3201", name="빈 작업", status="approved",
              created_at=datetime.fromisoformat("2026-10-09T00:00:00Z"), approved_by="김용접")
    with pytest.raises(ValueError, match="marking"):
        to_robot_json(job)
    with pytest.raises(ValueError, match="승인"):
        to_robot_json(job.model_copy(update={"status": "awaiting_approval"}))
