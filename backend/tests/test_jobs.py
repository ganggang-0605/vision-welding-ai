from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.api import jobs as jobs_api
from app.schemas import ApproveRequest
from app.store import JobStatusConflict

JOBS = "/workspaces/demo/jobs"
BLOCK = "block_a1"  # 데모 작업이 속한 프로젝트(블록)
P1, P2, P3 = "A1-P1 부재 표기", "A1-P2 부재 표기", "A1-P3 부재 표기"

JOB_KEYS = {
    "id", "workspace_id", "project_id", "name", "status", "assembly_path", "related_job_ids", "created_at",
    "approved_at", "approved_by", "marking", "welding_condition", "cell", "leg_lengths", "confidence", "evidence",
    "needs_review", "analysis_error", "analysis_stage", "analysis_stage_at",
}


def _names(res) -> list[str]:
    assert res.status_code == 200
    return [j["name"] for j in res.json()]


def test_demo_jobs_newest_first(client):
    jobs = client.get(JOBS).json()
    assert [j["name"] for j in jobs] == [P3, P2, P1]
    created = [datetime.fromisoformat(j["created_at"]) for j in jobs]
    assert created == sorted(created, reverse=True)
    assert all(j["created_at"].endswith("Z") for j in jobs)  # UTC 로 정규화
    assert all(set(j) == JOB_KEYS and j["workspace_id"] == "demo" and j["project_id"] == BLOCK for j in jobs)

    by_name = {j["name"]: j for j in jobs}
    p1, p2, p3 = by_name[P1], by_name[P2], by_name[P3]
    assert (p1["status"], p1["assembly_path"], p1["confidence"]["overall"]) == ("needs_review", "A1/L1/M2/S1/P-1", 68)
    assert p1["needs_review"]
    assert (p2["status"], p2["assembly_path"], p2["confidence"]["overall"]) == ("approved", "A1/L1/M2/S1/P-2", 94)
    assert p2["welding_condition"] == {
        "joint_type": "FILLET", "process": "GMAW", "position": "2F",
        "current_a": "420-440", "voltage_v": "35-37", "speed_cm_min": "60",
    }
    assert p2["approved_by"] == "[작업자]"
    assert p2["approved_at"] is not None
    assert (p3["status"], p3["assembly_path"], p3["confidence"]["overall"]) == ("awaiting_approval", "A1/L1/M2/S2/P-3", 86)
    assert p3["approved_at"] is None

    # 셀 형태 = PAC 과제 셀 예시 1·2·3, 각장 = F·V·S 수기 표기
    assert p1["cell"] == {"left": ["slit"], "right": ["slot"]}
    assert p2["cell"] == {"left": ["collar_back"], "right": ["slit"]}
    assert p3["cell"] == {"left": ["slit"], "right": ["collar_front", "scallop"]}
    assert [(leg["code"], leg["size_mm"]) for leg in p1["leg_lengths"]] == [("F", 5.5), ("V", 6.0)]
    assert p1["leg_lengths"][0] == {"code": "F", "size_mm": 5.5, "raw_text": "F5.5", "meaning": "3F 용접장 각장"}


@pytest.mark.parametrize("params, expected", [
    ({"q": "a1-p2"}, [P2]),                    # 이름 (대소문자 무시)
    ({"q": "s2/p"}, [P3]),                     # 조립 경로
    ({"q": "v6.0"}, [P1]),                     # 표기 원문
    ({"q": "2f 용접장"}, [P1]),                 # 해석
    ({"q": "부재"}, [P3, P2, P1]),
    ({"q": ""}, [P3, P2, P1]),
    ({"q": "", "status": ""}, [P3, P2, P1]),  # 빈 값은 필터 없음
    ({"q": "없는 작업"}, []),
    ({"status": "approved"}, [P2]),
    ({"status": "draft"}, []),
    ({"q": "f5.5", "status": "needs_review"}, [P1]),
    ({"q": "s5.0", "status": "approved"}, [P2]),
    ({"project_id": BLOCK}, [P3, P2, P1]),
    ({"project_id": ""}, [P3, P2, P1]),       # 빈 값은 필터 없음
    ({"project_id": "block_a2"}, []),         # 작업 없는 프로젝트
    ({"project_id": "nope"}, []),              # 없는 프로젝트 id 도 빈 목록
    ({"project_id": "practice"}, []),          # 다른 워크스페이스의 프로젝트
    ({"q": "f5.5", "project_id": BLOCK}, [P3, P1]),
])
def test_search_jobs(client, params, expected):
    assert _names(client.get(JOBS, params=params)) == expected


def test_search_jobs_invalid_status(client):
    assert client.get(JOBS, params={"status": "done"}).status_code == 422


def test_create_job(client):
    res = client.post(JOBS, json={
        "name": "A1-P4 부재 표기", "project_id": BLOCK, "assembly_path": "A1/L1/M2/S2/P-4", "related_job_ids": ["job_demo_p3"],
    })
    assert res.status_code == 201
    job = res.json()
    assert set(job) == JOB_KEYS
    assert job["status"] == "draft"
    assert job["workspace_id"] == "demo"
    assert job["project_id"] == BLOCK
    assert job["related_job_ids"] == ["job_demo_p3"]
    assert job["marking"] is job["confidence"] is job["approved_at"] is None
    assert job["evidence"] == job["needs_review"] == job["leg_lengths"] == []
    assert job["cell"] is None

    assert client.get(f"{JOBS}/{job['id']}").json() == job
    assert client.get(JOBS).json()[0] == job  # 최신순
    assert _names(client.get(JOBS, params={"status": "draft"})) == ["A1-P4 부재 표기"]


def test_create_job_defaults(client):
    job = client.post(JOBS, json={"name": "이름만", "project_id": BLOCK}).json()
    assert job["assembly_path"] is None
    assert job["related_job_ids"] == []


@pytest.mark.parametrize("body", [
    {}, {"name": "", "project_id": BLOCK}, {"name": "  ", "project_id": BLOCK}, {"assembly_path": "A1", "project_id": BLOCK},
])
def test_create_job_validation(client, body):
    assert client.post(JOBS, json=body).status_code == 422


def test_job_in_other_project_filter(client):
    """같은 워크스페이스의 다른 프로젝트 작업은 ?project_id= 로 나뉜다."""
    job = client.post(JOBS, json={"name": "3202 첫 작업", "project_id": "block_a2"}).json()
    assert job["project_id"] == "block_a2"
    assert _names(client.get(JOBS, params={"project_id": "block_a2"})) == ["3202 첫 작업"]
    assert _names(client.get(JOBS, params={"project_id": BLOCK})) == [P3, P2, P1]
    assert _names(client.get(JOBS)) == ["3202 첫 작업", P3, P2, P1]


@pytest.mark.parametrize("project_id", [None, "", "  ", "nope", "practice"])  # 누락·빈 값·없는 id·다른 워크스페이스
def test_create_job_requires_project(client, project_id):
    body = {"name": "x"} if project_id is None else {"name": "x", "project_id": project_id}
    res = client.post(JOBS, json=body)
    assert res.status_code == 422
    assert [e["loc"] for e in res.json()["detail"]] == [["body", "project_id"]]
    assert _names(client.get(JOBS)) == [P3, P2, P1]


def test_create_job_reports_project_and_related_errors_together(client):
    res = client.post(JOBS, json={"name": "x", "project_id": "nope", "related_job_ids": ["job_demo_p1", "gone"]})
    assert res.status_code == 422
    assert [(e["loc"], e["input"]) for e in res.json()["detail"]] == [
        (["body", "project_id"], "nope"), (["body", "related_job_ids", 1], "gone"),
    ]


def test_create_job_rejects_unknown_related_jobs(client):
    """관련 작업은 같은 워크스페이스의 작업만 — 없는 id·다른 워크스페이스의 id 면 422"""
    other = client.post("/workspaces", json={"name": "다른 조선소"}).json()["id"]
    project = client.post(f"/workspaces/{other}/projects", json={"name": "Z1 블록"}).json()["id"]
    res = client.post(f"/workspaces/{other}/jobs", json={"name": "x", "project_id": project, "related_job_ids": ["job_demo_p1"]})
    assert res.status_code == 422
    assert res.json()["detail"][0]["loc"] == ["body", "related_job_ids", 0]
    assert client.get(f"/workspaces/{other}/jobs").json() == []

    res = client.post(JOBS, json={"name": "x", "project_id": BLOCK, "related_job_ids": ["job_demo_p1", "nope"]})
    assert res.status_code == 422
    assert [e["input"] for e in res.json()["detail"]] == ["nope"]
    assert _names(client.get(JOBS)) == [P3, P2, P1]


def test_get_unknown_job(client):
    res = client.get(f"{JOBS}/nope")
    assert res.status_code == 404
    assert "작업" in res.json()["detail"]


def test_jobs_isolated_per_workspace(client):
    other = client.post("/workspaces", json={"name": "다른 조선소"}).json()["id"]
    other_jobs = f"/workspaces/{other}/jobs"
    # 데모 작업 id 를 다른 워크스페이스 경로로 요청하면 404
    assert client.get(f"{other_jobs}/job_demo_p1").status_code == 404
    assert client.post(f"{other_jobs}/job_demo_p3/approve", json={"approved_by": "김용접"}).status_code == 404
    assert client.get(f"{other_jobs}/job_demo_p2/export").status_code == 404
    assert client.get(f"{JOBS}/job_demo_p3").json()["status"] == "awaiting_approval"

    # 데모 프로젝트에도 작업을 만들 수 없다 (422)
    assert client.post(other_jobs, json={"name": "다른 작업", "project_id": BLOCK}).status_code == 422
    project = client.post(f"/workspaces/{other}/projects", json={"name": "Z1 블록"}).json()["id"]
    own = client.post(other_jobs, json={"name": "다른 작업", "project_id": project}).json()
    assert (own["workspace_id"], own["project_id"]) == (other, project)
    assert client.get(f"{JOBS}/{own['id']}").status_code == 404
    assert _names(client.get(other_jobs)) == ["다른 작업"]
    assert _names(client.get(JOBS)) == [P3, P2, P1]


# ── 해석 파이프라인 (사진·해석·작업자 확인 흐름은 test_analysis_api.py) ──

@pytest.mark.parametrize("action, kwargs", [
    ("images", {}),                                   # file 누락
    ("review", {"json": {"action": "guess"}}),         # 잘못된 action
])
def test_pipeline_validation(client, action, kwargs):
    assert client.post(f"{JOBS}/job_demo_p1/{action}", **kwargs).status_code == 422


# ── 승인 ──

@pytest.mark.parametrize("job_id, acknowledge", [("job_demo_p3", False), ("job_demo_p1", True)])  # 승인 대기 / 확인 필요
def test_approve(client, job_id, acknowledge):
    res = client.post(f"{JOBS}/{job_id}/approve", json={"approved_by": "김용접", "acknowledge_review": acknowledge})
    assert res.status_code == 200
    job = res.json()
    assert job["status"] == "approved"
    assert job["approved_by"] == "김용접"
    assert datetime.fromisoformat(job["approved_at"]).tzinfo is not None
    assert client.get(f"{JOBS}/{job_id}").json() == job
    # 이미 승인된 작업은 다시 승인할 수 없다
    assert client.post(f"{JOBS}/{job_id}/approve", json={"approved_by": "다른 사람"}).status_code == 409


def test_approve_needs_review_requires_acknowledgement(client):
    """확인 필요 작업은 작업자가 확인 항목을 직접 봤다고 표시해야 승인 (검증 없이 로봇 JSON 까지 가지 않게)"""
    res = client.post(f"{JOBS}/job_demo_p1/approve", json={"approved_by": "김용접"})
    assert res.status_code == 409 and "확인 필요 항목 2개" in res.json()["detail"]
    assert client.get(f"{JOBS}/job_demo_p1").json()["status"] == "needs_review"


def test_approve_requires_robot_fields(client, fresh_store):
    """조립 경로 · 표기 · 용접 조건이 비어 있으면 로봇 JSON 을 만들 수 없어 승인하지 않음 (확인 표시가 있어도)"""
    job = fresh_store.get_job("demo", "job_demo_p1")
    fresh_store.save_job(job.model_copy(update={"welding_condition": None}))
    res = client.post(f"{JOBS}/job_demo_p1/approve", json={"approved_by": "김용접", "acknowledge_review": True})
    assert res.status_code == 409 and "welding_condition" in res.json()["detail"]


def test_approve_draft_conflict(client):
    job = client.post(JOBS, json={"name": "초안", "project_id": BLOCK}).json()
    res = client.post(f"{JOBS}/{job['id']}/approve", json={"approved_by": "김용접"})
    assert res.status_code == 409
    assert client.get(f"{JOBS}/{job['id']}").json() == job


def test_approve_checks_current_status(client, fresh_store):
    """승인 가능 여부는 요청 시작 시점의 스냅샷이 아니라 저장소의 최신 상태로 판단한다."""
    stale = fresh_store.get_job("demo", "job_demo_p3")
    assert client.post(f"{JOBS}/job_demo_p3/approve", json={"approved_by": "A"}).status_code == 200
    with pytest.raises(HTTPException) as exc:
        jobs_api.approve_job(stale, ApproveRequest(approved_by="B"), fresh_store)
    assert exc.value.status_code == 409
    assert client.get(f"{JOBS}/job_demo_p3").json()["approved_by"] == "A"


def test_concurrent_approve_single_winner(fresh_store):
    def approve(i: int) -> str | None:
        try:
            return fresh_store.approve_job("demo", "job_demo_p3", f"작업자{i}").approved_by
        except JobStatusConflict:
            return None

    with ThreadPoolExecutor(8) as pool:
        winners = [w for w in pool.map(approve, range(32)) if w]
    assert len(winners) == 1
    assert fresh_store.get_job("demo", "job_demo_p3").approved_by == winners[0]


@pytest.mark.parametrize("body", [{}, {"approved_by": ""}, {"approved_by": "  "}])
def test_approve_requires_approver(client, body):
    assert client.post(f"{JOBS}/job_demo_p3/approve", json=body).status_code == 422


def test_store_isolated_between_tests(client):
    """다른 테스트에서 승인·생성한 내용이 남아 있지 않다 (conftest 의 reset_store)."""
    jobs = client.get(JOBS).json()
    assert [(j["name"], j["status"]) for j in jobs] == [
        (P3, "awaiting_approval"), (P2, "approved"), (P1, "needs_review"),
    ]
