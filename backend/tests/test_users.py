"""데모 다중 계정 — X-User-Id 헤더가 현재 사용자를 고른다 (인증 전 임시)"""
import pytest

DEMO = {"id": "user_kkm", "name": "김경무", "email": "gyeongmu.kim@vision-welding.local"}
PARK = {"id": "user_ldh", "name": "이동현", "email": "donghyun.lee@vision-welding.local"}
CHOI = {"id": "user_lmh", "name": "이민환", "email": "minhwan.lee@vision-welding.local"}


def _as(user_id: str) -> dict:
    return {"X-User-Id": user_id}


def _workspace_ids(client, **kwargs) -> list[str]:
    res = client.get("/workspaces", **kwargs)
    assert res.status_code == 200
    return [w["id"] for w in res.json()]


def test_list_users(client):
    res = client.get("/users")
    assert res.status_code == 200
    assert res.json() == [DEMO, PARK, CHOI]  # 시드 순


@pytest.mark.parametrize("headers, expected", [
    ({}, DEMO),                    # 헤더 없음 → 김경무
    (_as(""), DEMO),               # 빈 값도 김경무
    (_as("user_kkm"), DEMO),
    (_as("user_ldh"), PARK),
    (_as("user_lmh"), CHOI),
])
def test_me_from_header(client, headers, expected):
    assert client.get("/me", headers=headers).json() == expected


@pytest.mark.parametrize("method, path, kwargs", [
    ("GET", "/me", {}),
    ("GET", "/workspaces", {}),
    ("POST", "/workspaces", {"json": {"name": "몰래 만든 공간"}}),
])
def test_unknown_user_401(client, method, path, kwargs):
    before = _workspace_ids(client)
    res = client.request(method, path, headers=_as("user_nope"), **kwargs)
    assert res.status_code == 401
    assert res.json() == {"detail": "알 수 없는 사용자입니다: user_nope"}
    assert _workspace_ids(client) == before


@pytest.mark.parametrize("user_id, expected", [
    ("user_kkm", ["demo", "personal", "yeongam"]),
    ("user_ldh", ["demo", "ldh", "yeongam"]),
    ("user_lmh", ["demo"]),
])
def test_workspaces_filtered_by_member(client, user_id, expected):
    assert _workspace_ids(client, headers=_as(user_id)) == expected


def test_ldh_seed_workspace(client):
    ws = client.get("/workspaces/ldh").json()
    assert (ws["name"], ws["kind"], ws["member_count"]) == ("이동현의 워크스페이스", "personal", 1)
    assert [(m["user_id"], m["role"]) for m in client.get("/workspaces/ldh/members").json()] == [("user_ldh", "owner")]
    [project] = client.get("/workspaces/ldh/projects").json()
    assert (project["id"], project["name"]) == ("block_b1", "B1 블록")
    assert client.get("/workspaces/ldh/projects/block_b1/assembly-tree").json() == []
    assert client.get("/workspaces/ldh/jobs").json() == []


def test_create_workspace_as_header_user(client):
    res = client.post("/workspaces", json={"name": "이민환 공간"}, headers=_as("user_lmh"))
    assert res.status_code == 201
    ws = res.json()
    [owner] = client.get(f"/workspaces/{ws['id']}/members").json()
    assert (owner["user_id"], owner["name"], owner["role"]) == ("user_lmh", "이민환", "owner")
    # 만든 사람의 목록에만 보인다
    assert _workspace_ids(client, headers=_as("user_lmh")) == ["demo", ws["id"]]
    assert ws["id"] not in _workspace_ids(client)
    assert ws["id"] not in _workspace_ids(client, headers=_as("user_ldh"))
    # 목록만 거른다 — 경로로는 누구나 접근 (TODO 권한)
    assert client.get(f"/workspaces/{ws['id']}", headers=_as("user_ldh")).status_code == 200


def test_invited_user_sees_workspace(client):
    assert "personal" not in _workspace_ids(client, headers=_as("user_lmh"))
    client.post("/workspaces/personal/members", json={"name": "이민환", "email": "minhwan.lee@vision-welding.local"})
    assert _workspace_ids(client, headers=_as("user_lmh")) == ["demo", "personal"]


def test_invited_new_user_can_act(client):
    """초대로 새로 만든 사용자도 /users 에 나오고 X-User-Id 로 쓸 수 있다."""
    member = client.post(
        "/workspaces/personal/members", json={"name": "김용접", "email": "kim@vision-welding.local"}
    ).json()
    assert client.get("/users").json()[-1]["id"] == member["user_id"]
    assert client.get("/me", headers=_as(member["user_id"])).json()["name"] == "김용접"
    assert _workspace_ids(client, headers=_as(member["user_id"])) == ["personal"]
