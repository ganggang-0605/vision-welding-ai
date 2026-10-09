"""현재 사용자(/me), 워크스페이스 종류(개인/팀), 멤버 초대"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from app.store import MemberAlreadyExists

DEMO_USER = {"id": "user_kkm", "name": "김경무", "email": "gyeongmu.kim@vision-welding.local"}
MEMBER_KEYS = {"user_id", "name", "email", "role", "joined_at"}


def _invite(client, workspace_id: str, name: str, email: str):
    return client.post(f"/workspaces/{workspace_id}/members", json={"name": name, "email": email})


def test_me(client):
    res = client.get("/me")
    assert res.status_code == 200
    assert res.json() == DEMO_USER


def test_demo_members(client):
    """소유자 먼저, 그다음 가입 순"""
    members = client.get("/workspaces/demo/members").json()
    assert all(set(m) == MEMBER_KEYS for m in members)
    assert [(m["user_id"], m["role"]) for m in members] == [
        ("user_kkm", "owner"), ("user_ldh", "member"), ("user_lmh", "member"),
    ]
    assert members[0]["name"] == "김경무"
    assert all(m["email"].endswith("@vision-welding.local") for m in members)
    assert all(m["joined_at"].endswith("Z") for m in members)


def test_create_workspace_current_user_is_owner(client):
    ws = client.post("/workspaces", json={"name": "내 공간"}).json()
    assert (ws["kind"], ws["member_count"]) == ("personal", 1)
    [owner] = client.get(f"/workspaces/{ws['id']}/members").json()
    assert {k: owner[k] for k in ("user_id", "name", "email", "role")} == {
        "user_id": "user_kkm", "name": "김경무", "email": "gyeongmu.kim@vision-welding.local", "role": "owner",
    }
    assert datetime.fromisoformat(owner["joined_at"]) == datetime.fromisoformat(ws["created_at"])


def test_create_team_workspace(client):
    ws = client.post("/workspaces", json={"name": "용접 2팀", "kind": "team"}).json()
    assert (ws["kind"], ws["member_count"]) == ("team", 1)
    assert [m["role"] for m in client.get(f"/workspaces/{ws['id']}/members").json()] == ["owner"]


def test_invite_turns_personal_into_team(client):
    res = _invite(client, "personal", "  김용접 ", " kim.weld@vision-welding.local ")
    assert res.status_code == 201
    member = res.json()
    assert set(member) == MEMBER_KEYS
    assert (member["name"], member["email"], member["role"]) == ("김용접", "kim.weld@vision-welding.local", "member")
    assert member["user_id"].startswith("user_")

    ws = client.get("/workspaces/personal").json()
    assert (ws["kind"], ws["member_count"]) == ("team", 2)
    assert [m["user_id"] for m in client.get("/workspaces/personal/members").json()] == ["user_kkm", member["user_id"]]
    # 같은 사용자를 다른 워크스페이스에 초대하면 같은 user_id
    other = client.post("/workspaces", json={"name": "3도크"}).json()["id"]
    assert _invite(client, other, "다른 이름", "KIM.WELD@vision-welding.local").json()["user_id"] == member["user_id"]


def test_invite_reuses_existing_user(client):
    """이메일이 같은 사용자(대소문자 무시)가 있으면 새로 만들지 않고 그 사용자를 초대한다 — 이름은 기존 그대로."""
    member = _invite(client, "personal", "다른 이름", "Donghyun.Lee@vision-welding.local").json()
    assert (member["user_id"], member["name"], member["email"]) == (
        "user_ldh", "이동현", "donghyun.lee@vision-welding.local",
    )


@pytest.mark.parametrize("email", [
    "donghyun.lee@vision-welding.local",
    "DONGHYUN.LEE@VISION-WELDING.LOCAL",
    "gyeongmu.kim@vision-welding.local",  # 소유자
])
def test_duplicate_invite_conflict(client, email):
    before = client.get("/workspaces/demo").json()
    res = _invite(client, "demo", "중복", email)
    assert res.status_code == 409
    assert "멤버" in res.json()["detail"]
    assert client.get("/workspaces/demo").json() == before
    assert len(client.get("/workspaces/demo/members").json()) == 3


def test_invite_twice_conflict(client):
    assert _invite(client, "personal", "김용접", "kim@vision-welding.local").status_code == 201
    assert _invite(client, "personal", "김용접", "Kim@Vision-Welding.local").status_code == 409
    assert client.get("/workspaces/personal").json()["member_count"] == 2


@pytest.mark.parametrize("body", [
    {"name": "김용접", "email": "kim.vision-welding.local"},  # '@' 없음
    {"name": "김용접", "email": ""},
    {"name": "김용접"},
    {"name": "", "email": "kim@vision-welding.local"},
    {"name": "  ", "email": "kim@vision-welding.local"},
    {"email": "kim@vision-welding.local"},
])
def test_invite_validation(client, body):
    res = client.post("/workspaces/personal/members", json=body)
    assert res.status_code == 422
    ws = client.get("/workspaces/personal").json()
    assert (ws["kind"], ws["member_count"]) == ("personal", 1)


def test_invite_without_at_reports_email(client):
    res = _invite(client, "personal", "김용접", "kim")
    assert [e["loc"] for e in res.json()["detail"]] == [["body", "email"]]


def test_concurrent_duplicate_invite_single_winner(fresh_store):
    def invite(i: int) -> bool:
        try:
            fresh_store.invite_member("personal", f"작업자{i}", "same@vision-welding.local")
            return True
        except MemberAlreadyExists:
            return False

    with ThreadPoolExecutor(8) as pool:
        assert sum(pool.map(invite, range(32))) == 1
    assert fresh_store.get_workspace("personal").member_count == 2
    assert len(fresh_store.list_members("personal")) == 2


# ── 워크스페이스 수정 (PATCH) ──

def test_update_workspace_fields(client):
    res = client.patch("/workspaces/personal", json={"name": "  내 연습 공간 ", "description": "혼자 연습"})
    assert res.status_code == 200
    ws = res.json()
    assert (ws["name"], ws["description"], ws["kind"]) == ("내 연습 공간", "혼자 연습", "personal")
    assert client.get("/workspaces/personal").json() == ws
    # description 만 null 로 비울 수 있다 — 보내지 않은 필드는 그대로
    ws = client.patch("/workspaces/personal", json={"description": None}).json()
    assert (ws["name"], ws["description"]) == ("내 연습 공간", None)
    assert client.patch("/workspaces/personal", json={}).json() == ws


@pytest.mark.parametrize("body", [
    {"name": None}, {"name": ""}, {"name": "   "}, {"name": "x" * 101}, {"kind": None}, {"kind": "shared"},
])
def test_update_workspace_validation(client, body):
    assert client.patch("/workspaces/personal", json=body).status_code == 422


def test_personal_to_team_and_back(client):
    ws = client.patch("/workspaces/personal", json={"kind": "team"}).json()
    assert (ws["kind"], ws["member_count"]) == ("team", 1)
    # 멤버가 1명이면 다시 개인으로 바꿀 수 있다
    assert client.patch("/workspaces/personal", json={"kind": "personal"}).json()["kind"] == "personal"


def test_team_to_personal_conflict_with_members(client):
    res = client.patch("/workspaces/demo", json={"kind": "personal", "name": "바뀌면 안 됨"})
    assert res.status_code == 409
    assert "멤버" in res.json()["detail"]
    ws = client.get("/workspaces/demo").json()
    assert (ws["name"], ws["kind"], ws["member_count"]) == ("울산 1도크", "team", 3)
    # team 으로 두는 수정은 된다
    assert client.patch("/workspaces/demo", json={"kind": "team", "name": "1도크"}).json()["name"] == "1도크"


def test_invited_workspace_cannot_go_back_to_personal(client):
    _invite(client, "personal", "김용접", "kim@vision-welding.local")
    assert client.patch("/workspaces/personal", json={"kind": "personal"}).status_code == 409
    assert client.get("/workspaces/personal").json()["kind"] == "team"
