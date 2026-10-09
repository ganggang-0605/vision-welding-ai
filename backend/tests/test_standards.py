def test_welding_standards(client):
    res = client.get("/welding-standards")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 3
    assert rows[0] == {
        "joint_type": "FILLET", "thickness_min_mm": 6, "thickness_max_mm": 12, "process": "FCAW",
        "position": "FLAT", "current_a": "220-260", "voltage_v": "26-30", "speed_cm_min": "30-40",
    }
    assert {r["joint_type"] for r in rows} == {"FILLET", "BUTT_V"}


def test_welding_standards_are_global(client):
    """표준 용접 기준은 워크스페이스와 무관한 공통 데이터다."""
    before = client.get("/welding-standards").json()
    client.post("/workspaces", json={"name": "2도크"})
    assert client.get("/welding-standards").json() == before
    assert client.get("/workspaces/demo/welding-standards").status_code == 404
