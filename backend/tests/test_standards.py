def test_welding_standards(client):
    res = client.get("/welding-standards")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 14
    assert rows[0] == {  # 다이도 특수강 溶接施工 표 5·8 (data/seed/SOURCES.md)
        "joint_type": "FILLET", "thickness_min_mm": 3.2, "thickness_max_mm": 3.2, "leg_min_mm": 3, "leg_max_mm": 3,
        "process": "GMAW", "position": "2F", "current_a": "310-320", "voltage_v": "30-31", "speed_cm_min": "120",
    }
    assert {r["joint_type"] for r in rows} == {"FILLET", "BUTT_I"}
    assert {r["position"] for r in rows} == {"1F", "2F", "3F", "1G"}


def test_vertical_fillet_rows_have_leg_lengths_only(client):
    """3F 수직 필렛(표 5·12 상진)은 출처가 각장별 값만 줘서 판 두께가 없다 — 수기 각장 F(3F 용접장)로 고른다"""
    rows = [r for r in client.get("/welding-standards").json() if r["position"] == "3F"]
    assert [(r["thickness_min_mm"], r["leg_min_mm"], r["current_a"]) for r in rows] == [
        (None, 5, "110-140"), (None, 8, "120-150"), (None, 12, "130-180")]


def test_welding_standards_are_global(client):
    """표준 용접 기준은 워크스페이스와 무관한 공통 데이터다."""
    before = client.get("/welding-standards").json()
    client.post("/workspaces", json={"name": "2도크"})
    assert client.get("/welding-standards").json() == before
    assert client.get("/workspaces/demo/welding-standards").status_code == 404
