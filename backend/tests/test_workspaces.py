import pytest

SYMBOLS = "/workspaces/demo/symbols"


def test_list_workspaces_includes_demo(client):
    res = client.get("/workspaces")
    assert res.status_code == 200
    [demo] = [w for w in res.json() if w["id"] == "demo"]
    assert demo["name"] == "데모 조선소 · 1도크"
    assert set(demo) == {"id", "name", "description", "created_at"}


def test_create_and_get_workspace(client):
    res = client.post("/workspaces", json={"name": "  2도크  ", "description": "용접 2팀"})
    assert res.status_code == 201
    ws = res.json()
    assert ws["name"] == "2도크"
    assert ws["description"] == "용접 2팀"
    assert ws["id"] != "demo"

    assert client.get(f"/workspaces/{ws['id']}").json() == ws
    assert ws in client.get("/workspaces").json()
    # 새 워크스페이스는 사전·조립 트리·작업이 비어 있다 (dictionary_source 기본값 "empty")
    for sub in ("symbols", "assembly-tree", "jobs"):
        assert client.get(f"/workspaces/{ws['id']}/{sub}").json() == []


def test_create_workspace_without_description(client):
    ws = client.post("/workspaces", json={"name": "3도크"}).json()
    assert ws["description"] is None


@pytest.mark.parametrize("body", [
    {},
    {"name": ""},
    {"name": "   "},
    {"name": "x" * 101},
    {"name": "복사", "dictionary_source": "copy"},
    {"name": "복사", "dictionary_source": "copy", "copy_from_workspace_id": None},
    {"name": "잘못된 원본", "dictionary_source": "template"},
])
def test_create_workspace_validation(client, body):
    assert client.post("/workspaces", json=body).status_code == 422


def test_get_unknown_workspace(client):
    assert client.get("/workspaces/nope").status_code == 404


@pytest.mark.parametrize("method, path, kwargs", [
    ("GET", "/symbols", {}),
    ("POST", "/symbols", {"json": {"code": "FW", "kind": "text", "meaning": "필렛"}}),
    ("PATCH", "/symbols/sym_fw", {"json": {"meaning": "필렛"}}),
    ("DELETE", "/symbols/sym_fw", {}),
    ("GET", "/assembly-tree", {}),
    ("GET", "/jobs", {}),
    ("POST", "/jobs", {"json": {"name": "작업"}}),
    ("GET", "/jobs/job_demo_p1", {}),
    ("POST", "/jobs/job_demo_p1/images", {"files": {"file": ("m.jpg", b"\xff\xd8\xff", "image/jpeg")}}),
    ("POST", "/jobs/job_demo_p1/analyze", {}),
    ("POST", "/jobs/job_demo_p1/review", {"json": {"action": "manual"}}),
    ("POST", "/jobs/job_demo_p3/approve", {"json": {"approved_by": "김용접"}}),
    ("GET", "/jobs/job_demo_p2/export", {}),
])
def test_unknown_workspace_404_on_nested_routes(client, method, path, kwargs):
    res = client.request(method, f"/workspaces/nope{path}", **kwargs)
    assert res.status_code == 404
    assert "워크스페이스" in res.json()["detail"]


# ── 문자/기호 사전 ──

def test_demo_symbols(client):
    entries = {e["id"]: e for e in client.get(SYMBOLS).json()}
    assert entries["sym_fw"] == {
        "id": "sym_fw", "code": "FW", "kind": "text", "meaning": "필렛 용접 (Fillet Weld)",
        "aliases": ["F/W"], "welding_joint_type": "FILLET",
    }
    assert entries["sym_bv"]["welding_joint_type"] == "BUTT_V"
    assert entries["sym_field"]["kind"] == "symbol"
    assert entries["sym_field"]["welding_joint_type"] is None


def test_symbol_crud(client):
    res = client.post(SYMBOLS, json={"code": "CW", "kind": "text", "meaning": "모서리 용접"})
    assert res.status_code == 201
    created = res.json()
    assert created["aliases"] == []
    assert created["welding_joint_type"] is None
    sid = created["id"]
    assert created in client.get(SYMBOLS).json()

    # 보낸 필드만 바뀐다
    res = client.patch(f"{SYMBOLS}/{sid}", json={"aliases": ["C/W"], "welding_joint_type": "CORNER"})
    assert res.status_code == 200
    assert res.json() == {**created, "aliases": ["C/W"], "welding_joint_type": "CORNER"}
    # welding_joint_type 만 null 로 비울 수 있다
    assert client.patch(f"{SYMBOLS}/{sid}", json={"welding_joint_type": None}).json()["welding_joint_type"] is None
    for field in ("code", "kind", "meaning", "aliases"):
        assert client.patch(f"{SYMBOLS}/{sid}", json={field: None}).status_code == 422
    assert client.patch(f"{SYMBOLS}/{sid}", json={"kind": "image"}).status_code == 422

    res = client.delete(f"{SYMBOLS}/{sid}")
    assert res.status_code == 204
    assert res.content == b""
    assert sid not in [e["id"] for e in client.get(SYMBOLS).json()]
    assert client.delete(f"{SYMBOLS}/{sid}").status_code == 404
    assert client.patch(f"{SYMBOLS}/{sid}", json={"meaning": "x"}).status_code == 404


@pytest.mark.parametrize("body", [
    {"kind": "text", "meaning": "코드 없음"},
    {"code": "", "kind": "text", "meaning": "빈 코드"},
    {"code": "X", "kind": "image", "meaning": "잘못된 kind"},
])
def test_create_symbol_validation(client, body):
    assert client.post(SYMBOLS, json=body).status_code == 422


def _without_ids(entries: list[dict]) -> list[dict]:
    return [{k: v for k, v in e.items() if k != "id"} for e in entries]


def test_create_workspace_copies_dictionary(client):
    demo_symbols = client.get(SYMBOLS).json()
    res = client.post("/workspaces", json={
        "name": "2도크", "dictionary_source": "copy", "copy_from_workspace_id": "demo",
    })
    assert res.status_code == 201
    ws_id = res.json()["id"]

    copied = client.get(f"/workspaces/{ws_id}/symbols").json()
    assert _without_ids(copied) == _without_ids(demo_symbols)
    # 복사본은 독립적이다 — 수정·삭제해도 원본은 그대로
    client.patch(f"/workspaces/{ws_id}/symbols/{copied[0]['id']}", json={"aliases": ["바뀜"]})
    client.delete(f"/workspaces/{ws_id}/symbols/{copied[1]['id']}")
    assert client.get(SYMBOLS).json() == demo_symbols
    # 사전만 복사하고 조립 트리·작업은 복사하지 않는다
    assert client.get(f"/workspaces/{ws_id}/assembly-tree").json() == []
    assert client.get(f"/workspaces/{ws_id}/jobs").json() == []


def test_copy_dictionary_from_unknown_workspace(client):
    before = client.get("/workspaces").json()
    res = client.post("/workspaces", json={
        "name": "2도크", "dictionary_source": "copy", "copy_from_workspace_id": "nope",
    })
    assert res.status_code == 404
    assert client.get("/workspaces").json() == before


def test_empty_dictionary_ignores_copy_source(client):
    res = client.post("/workspaces", json={"name": "2도크", "copy_from_workspace_id": "demo"})
    assert res.status_code == 201
    assert client.get(f"/workspaces/{res.json()['id']}/symbols").json() == []
