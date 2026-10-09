import copy
import json
import threading

import pytest
from vw_shared import load_example, schema_errors, semantic_errors

from db_context_interpreter import interpret
from db_context_interpreter import vlm as vlm_module

VISION = load_example("vision_result.example.json")
CONTEXT_INPUT = load_example("context_input.example.json")
EXPECTED = load_example("context_result.example.json")


@pytest.fixture(autouse=True)
def vlm_off(monkeypatch):
    """개발자 환경 변수와 상관없이 VLM을 끄고 시작 (켜는 테스트는 fake_vlm)"""
    monkeypatch.delenv("VLM_PROVIDER", raising=False)


def fake_vlm(monkeypatch, *responses: dict, runs: int | None = None):
    """VLM_PROVIDER=claude로 켜되 실제 API 대신 responses를 차례로 돌려줌 (마지막 것을 반복). 추론은 동시에 불리므로 잠금"""
    calls = []
    lock = threading.Lock()

    def generate(system, prompt, image, model):
        with lock:
            calls.append({"prompt": prompt, "image": image, "model": model})
            response = responses[min(len(calls), len(responses)) - 1]
        return json.dumps(response, ensure_ascii=False), None

    monkeypatch.setenv("VLM_PROVIDER", "claude")
    monkeypatch.setenv("VLM_RUNS", str(runs or len(responses)))
    monkeypatch.setitem(vlm_module.PROVIDERS, "claude", generate)
    return calls


def check(vision: dict, context: dict) -> dict:
    assert schema_errors(context, "context_result.schema.json") == []
    assert semantic_errors({"vision": vision, "context": context, "confidence": None}) == []
    return context


def run(vision=VISION, **changes) -> dict:
    return check(vision, interpret(vision, {**CONTEXT_INPUT, **changes}))


def vision_with(texts=(), symbols=()) -> dict:
    """1단계 결과 만들기: texts = [(text, prob) | (text, prob, candidates)]"""
    v = copy.deepcopy(VISION)
    v["texts"] = []
    for i, (text, prob, *cands) in enumerate(texts, 1):
        t = {"id": f"t{i}", "text": text, "prob": prob, "bbox": [10 + 100 * i, 10, 90 + 100 * i, 50], "source": "paddleocr"}
        if cands:
            t["candidates"] = [{"text": text, "prob": prob}] + [{"text": c, "prob": p} for c, p in cands[0]]
        v["texts"].append(t)
    v["symbols"] = [
        {"id": f"s{i}", "label": label, "prob": prob, "bbox": [10, 100, 50, 140], "source": "yolox"}
        for i, (label, prob) in enumerate(symbols, 1)
    ]
    return v


def types(context: dict) -> list[str]:
    return [c["type"] for c in context["conflicts"]]


VLM_EXAMPLE = {
    "interpretation": "부재 P-1(A1/L1/M2/S1/P-1), 필렛 용접, 판 두께 10mm, 현장 용접",
    "texts": [{"text": "P-1", "ref_id": "t1", "bbox": None}, {"text": "FW", "ref_id": "t2", "bbox": None},
              {"text": "t=10", "ref_id": "t3", "bbox": None}],
    "symbols": [{"label": "▲", "ref_id": "s1", "bbox": None}],
    "meanings": [{"ref_id": "t3", "meaning": "판 두께 10mm"}],
}


# ── 계약 ──

def test_output_matches_schema():
    result = interpret(VISION, CONTEXT_INPUT)
    assert schema_errors(result, "context_result.schema.json") == []


def test_refs_point_to_vision_result():
    """2단계가 가리키는 ID(ref_ids)가 1단계 결과나 VLM이 붙인 v*에 있는지"""
    analysis = {"vision": VISION, "context": interpret(VISION, CONTEXT_INPUT), "confidence": None}
    assert semantic_errors(analysis) == []


def test_keeps_user_context():
    result = interpret(VISION, {**CONTEXT_INPUT, "user_context": "8이 아니라 6입니다"})
    assert result["user_context"] == "8이 아니라 6입니다"


# ── 예시 (VLM 없이) ──

def test_example_without_vlm():
    result = run()
    assert result["part"] == EXPECTED["part"]
    assert result["welding_condition"] == EXPECTED["welding_condition"]
    by_ref = {m["ref_ids"][0]: m for m in result["dictionary_matches"]}
    assert set(by_ref) == {"t2", "t3", "s1"}  # t1(P-1)은 부재 번호라 사전 대조에서 빠짐
    assert (by_ref["t2"]["code"], by_ref["t2"]["match"], by_ref["t2"]["score"]) == ("FW", "exact", 0.62)
    assert (by_ref["s1"]["code"], by_ref["s1"]["match"]) == ("▲", "exact")
    assert (by_ref["t3"]["code"], by_ref["t3"]["match"], by_ref["t3"]["meaning"]) == (None, "none", "판 두께 10mm")
    assert types(result) == ["dictionary_unmatched"]
    assert result["vlm"] is None and result["related_job_ids"] == []


# ── 문자/기호 사전 ──

def test_alias_and_case_insensitive():
    result = run(vision_with([("f/w", 0.9), ("bv", 0.8)]))
    assert [(m["code"], m["match"]) for m in result["dictionary_matches"]] == [("FW", "alias"), ("BV", "exact")]


def test_leg_length_marking():
    """수기 각장 F·V·S + 숫자 → 사전의 F·V·S 항목, 의미에 mm 값"""
    result = run(vision_with([("F5.5", 0.93), ("V 6.0", 0.64), ("S4", 0.9)]))
    assert [(m["code"], m["meaning"]) for m in result["dictionary_matches"]] == [
        ("F", "3F 용접장 각장 5.5mm"), ("V", "2F 용접장 각장 6.0mm"), ("S", "스티프너 각장 4mm"),
    ]
    assert [(leg["code"], leg["size_mm"], leg["raw_text"], leg["meaning"], leg["ref_ids"]) for leg in result["leg_lengths"]] == [
        ("F", 5.5, "F5.5", "3F 용접장 각장", ["t1"]), ("V", 6.0, "V6.0", "2F 용접장 각장", ["t2"]),
        ("S", 4.0, "S4", "스티프너 각장", ["t3"])]
    # 판 두께가 없어 첫 번째 각장(F5.5 = 3F)으로 기준 행을 고름 — 기준표 3F는 각장 5 · 8 · 12라 가장 가까운 5mm + 작업자 확인
    wc = result["welding_condition"]
    assert (wc["position"], wc["current_a"], wc["leg_length_mm"], wc["standard_matched"]) == ("3F", "110-140", 5.5, False)
    assert ("standard_conflict", "warning") in [(c["type"], c["severity"]) for c in result["conflicts"]]


def test_candidate_match():
    result = run(vision_with([("EW", 0.5, [("FW", 0.4)])]))
    (m,) = result["dictionary_matches"]
    assert (m["raw"], m["code"], m["match"], m["score"]) == ("FW", "FW", "candidate", 0.4)


def test_ambiguous_candidates():
    """후보끼리 확률이 붙어 있고 사전 해석이 달라지면 ambiguous_reading"""
    result = run(vision_with([("FW", 0.45, [("BV", 0.4)])]))
    assert result["dictionary_matches"][0]["code"] == "FW"
    assert "ambiguous_reading" in types(result)


def test_leg_length_candidates_differ_by_value():
    """코드는 같고 숫자만 다른 후보(V6.0 ↔ V6.5)도 해석이 갈리는 것으로 봄. 같은 값(V6 ↔ V6.0)은 아님"""
    assert "ambiguous_reading" in types(run(vision_with([("V6.0", 0.5, [("V6.5", 0.4)])])))
    assert "ambiguous_reading" not in types(run(vision_with([("V6.0", 0.5, [("V6", 0.4)])])))


def test_fuzzy_and_unmatched():
    result = run(vision_with([("FWW", 0.9), ("XYZ", 0.9)]))
    fuzzy, none = result["dictionary_matches"]
    assert (fuzzy["code"], fuzzy["match"]) == ("FW", "fuzzy")
    assert (none["code"], none["match"], none["meaning"]) == (None, "none", None)
    assert [(c["type"], c["severity"]) for c in result["conflicts"]] == [
        ("dictionary_unmatched", "info"), ("dictionary_unmatched", "warning"),
    ]


def test_unknown_symbol():
    result = run(vision_with(symbols=[("unknown", 0.7)]))
    assert result["dictionary_matches"][0]["match"] == "none"


# ── 실제 OCR 출력: 한 줄로 붙은 표기 · 헷갈리는 글자 (vision/reports/phase1_baseline.md) ──

def test_one_line_is_split_into_markings():
    """PaddleOCR이 표기 여러 개를 한 줄(t1)로 읽어도 나눠서 해석하고, 근거는 모두 t1"""
    result = run(vision_with([("P-1 FW t=10", 0.95)]))
    assert result["part"]["assembly_path"] == "A1/L1/M2/S1/P-1" and result["part"]["ref_ids"] == ["t1"]
    assert [(m["raw"], m["code"], m["ref_ids"]) for m in result["dictionary_matches"]] == [
        ("FW", "FW", ["t1"]), ("t=10", None, ["t1"])]
    assert result["welding_condition"]["current_a"] == "420-440" and result["welding_condition"]["ref_ids"] == ["t1"]


def test_leg_lengths_on_one_line():
    result = run(vision_with([("P-2", 0.95), ("F5.5 V6.0", 0.93)]))
    assert [(m["code"], m["meaning"], m["ref_ids"]) for m in result["dictionary_matches"]] == [
        ("F", "3F 용접장 각장 5.5mm", ["t2"]), ("V", "2F 용접장 각장 6.0mm", ["t2"])]


@pytest.mark.parametrize("line", ["t = 10", "t=10", "T 10"])
def test_spaced_marking_kept_together(line):
    """공백이 끼어도 붙여야 뜻이 되는 표기(t = 10)는 나누지 않음"""
    result = run(vision_with([("FW", 0.9), (line, 0.9)]))
    assert result["welding_condition"]["thickness_mm"] == 10
    assert len(result["dictionary_matches"]) == 2


def test_confused_characters_in_part_and_thickness():
    """1→I, 0→O로 읽어도 조립 트리 · 판 두께를 찾고, 보정했다는 항목을 남김"""
    result = run(vision_with([("P-I", 0.99), ("FW", 0.9), ("t=1O", 0.98)]))
    assert result["part"]["assembly_path"] == "A1/L1/M2/S1/P-1"
    assert result["welding_condition"]["thickness_mm"] == 10
    t3 = next(m for m in result["dictionary_matches"] if m["ref_ids"] == ["t3"])
    assert (t3["raw"], t3["meaning"]) == ("T=10", "판 두께 10mm")
    assert ("ambiguous_reading", "info", ["t1"]) in [(c["type"], c["severity"], c["ref_ids"]) for c in result["conflicts"]]


@pytest.mark.parametrize("text, code, meaning", [
    ("F5,5", "F", "3F 용접장 각장 5.5mm"),   # 소수점을 쉼표로
    ("V6.O", "V", "2F 용접장 각장 6.0mm"),   # 0 → O
    ("54.5", "S", "스티프너 각장 4.5mm"),    # S → 5
])
def test_confused_characters_in_leg_length(text, code, meaning):
    (m,) = run(vision_with([(text, 0.9)]))["dictionary_matches"]
    assert (m["code"], m["meaning"], m["match"], m["score"]) == (code, meaning, "fuzzy", 0.81)


def test_exact_reading_wins_over_fix():
    """그대로 맞는 읽기는 보정하지 않음 (FW · S1 · 10t)"""
    result = run(vision_with([("S1", 0.9), ("FW", 0.9), ("10t", 0.9)]))
    assert result["part"]["node_id"] == "S1"
    assert [m["match"] for m in result["dictionary_matches"]] == ["exact", "none"]
    assert "ambiguous_reading" not in types(result)


def test_corrected_line_is_split_too():
    result = run(vision_with([("PI FVV", 0.6)]), corrections=[{"target": "t1", "value": "P-1 FW t=10"}])
    assert result["welding_condition"]["current_a"] == "420-440"
    assert result["conflicts"] == []  # 작업자가 고친 값은 확인된 것


def test_vlm_compares_whole_line(monkeypatch):
    """줄을 나눠도 OCR↔VLM 비교는 1단계가 읽은 줄 전체 기준"""
    fake_vlm(monkeypatch, {"interpretation": "부재 P-1, 필렛 용접, 판 두께 10mm",
                           "texts": [{"text": "P-1 FW t=10", "ref_id": "t1", "bbox": None}], "symbols": [], "meanings": []}, runs=1)
    result = run(vision_with([("P-1 FW t=10", 0.95)]))
    assert "ocr_vlm_mismatch" not in types(result)


# ── 조립 경로 ──

def test_part_without_dash_and_deepest_node():
    result = run(vision_with([("S2", 0.9), ("P3", 0.8)]))
    assert result["part"] == {"node_id": "P-3", "assembly_path": "A1/L1/M2/S2/P-3", "level": "PART",
                              "found_in_tree": True, "ref_ids": ["t1", "t2"]}


def test_part_on_different_branches_is_ambiguous():
    result = run(vision_with([("P-1", 0.9), ("P-3", 0.8), ("FW", 0.9)]))
    assert result["part"]["node_id"] == "P-1"
    assert types(result) == ["ambiguous_reading"]  # P-3은 부재 표기라 '사전에 없음'으로 다시 세지 않음
    assert [m["raw"] for m in result["dictionary_matches"]] == ["FW"]


def test_part_not_in_tree():
    result = run(vision_with([("P-9", 0.9)]))
    assert result["part"] == {"node_id": "P-9", "assembly_path": None, "level": None, "found_in_tree": False, "ref_ids": ["t1"]}
    assert types(result) == ["part_not_in_tree"]


def test_no_part():
    assert run(vision_with([("FW", 0.9)]), job_assembly_path=None)["part"]["assembly_path"] is None


# ── 용접 기준 ──

# 기준표: data/seed/welding_standards.csv (다이도 특수강 溶接施工, 판 두께별 값 — data/seed/SOURCES.md)

@pytest.mark.parametrize("thickness, position, current, assumed", [
    ("t=10", "2F", "420-440", False),  # 10mm는 2F 행만 있음
    ("T12", "1F", "450-480", False),   # 12mm는 1F 행만 있음
    ("t=8", "2F", "420-440", True),    # 8mm는 1F · 2F 둘 다 → 자세 표기가 없으면 2F + 경고
])
def test_standard_row_by_thickness(thickness, position, current, assumed):
    result = run(vision_with([("FW", 0.9), (thickness, 0.9)]))
    wc = result["welding_condition"]
    assert (wc["position"], wc["current_a"], wc["process"], wc["standard_matched"]) == (position, current, "GMAW", True)
    assert ("standard_conflict" in types(result)) == assumed


def test_thickness_not_in_table():
    """기준표는 판 두께별 값이라 사이 두께(7mm)는 지어내지 않고 작업자 확인"""
    result = run(vision_with([("FW", 0.9), ("t=7", 0.9)]))
    assert result["welding_condition"] is None
    (conflict,) = [c for c in result["conflicts"] if c["type"] == "standard_conflict"]
    assert conflict["severity"] == "error" and "3.2, 4.5, 6, 8, 10, 12" in conflict["message"]


@pytest.mark.parametrize("marking, position, current", [
    ("V6", "2F", "420-440"),   # V = 2F 용접장 각장
    ("PB", "2F", "420-440"),   # 수평수직필릿 자세 (AWS 2F)
    ("PA", "1F", "300-350"),   # 아래보기자세 (AWS 1F·1G) → 필렛이면 1F
])
def test_position_from_dictionary(marking, position, current):
    """사전 항목의 뜻에 적힌 자세로 기준 행을 고름 (경고 없음)"""
    result = run(vision_with([("FW", 0.9), (marking, 0.9), ("t=8", 0.9)]))
    assert (result["welding_condition"]["position"], result["welding_condition"]["current_a"]) == (position, current)
    assert "standard_conflict" not in types(result)
    assert "t2" in result["welding_condition"]["ref_ids"]


def test_position_without_thickness_rows_uses_leg_length():
    """F = 3F 용접장 각장인데 기준표의 3F 행은 각장별 값만 있음 → 판 두께 대신 각장으로 고르고, 다른 자세로 바꾸지 않음"""
    result = run(vision_with([("F5.5", 0.9), ("t=8", 0.9)]))
    wc = result["welding_condition"]
    assert (wc["position"], wc["thickness_mm"], wc["leg_length_mm"]) == ("3F", 8, 5.5)
    assert any(c["type"] == "standard_conflict" and "3F" in c["message"] for c in result["conflicts"])


@pytest.mark.parametrize("marking, position, current, matched", [
    ("V5", "2F", "420-440", True),    # 2F 각장 5 = 판 두께 6mm 행 (표 5·8)
    ("F8", "3F", "120-150", True),    # 3F 상진 각장 8 (표 5·12)
    ("F5.0", "3F", "110-140", True),
    ("V4.5", "2F", "420-440", False),  # 4와 5 사이 → 가까운 쪽(같으면 큰 각장) + 작업자 확인
])
def test_standard_row_by_leg_length(marking, position, current, matched):
    """PAC 손글씨처럼 판 두께 없이 각장만 있으면 각장으로 기준 행을 고름 (data/seed/SOURCES.md 각장 자료)"""
    result = run(vision_with([(marking, 0.95)]))
    wc = result["welding_condition"]
    assert (wc["position"], wc["current_a"], wc["standard_matched"]) == (position, current, matched)
    assert wc["ref_ids"] == ["t1"]
    assert ("standard_conflict" in types(result)) != matched


def test_several_leg_lengths_use_the_first():
    result = run(vision_with([("F5.0", 0.95), ("V5", 0.95)]))
    assert result["welding_condition"]["position"] == "3F"
    note = next(c for c in result["conflicts"] if c["type"] == "standard_conflict")
    assert note["severity"] == "info" and note["ref_ids"] == ["t2"]


def test_leg_length_missing_decimal_point_is_fixed():
    """'F55'는 각장 55mm가 아니라 소수점이 빠진 5.5mm로 보고 작업자 확인"""
    result = run(vision_with([("F55", 0.9)]))
    (m,) = result["dictionary_matches"]
    assert (m["raw"], m["meaning"], m["match"]) == ("F5.5", "3F 용접장 각장 5.5mm", "fuzzy")
    assert result["leg_lengths"][0]["size_mm"] == 5.5
    assert [(c["type"], c["severity"]) for c in result["conflicts"] if c["type"] == "ambiguous_reading"] == [
        ("ambiguous_reading", "warning")]


def test_implausible_leg_length_is_not_trusted():
    result = run(vision_with([("F120", 0.9)]))
    assert result["leg_lengths"] == [] and result["dictionary_matches"][0]["match"] == "none"
    assert any("현실적인 크기가 아니라" in c["message"] for c in result["conflicts"])


def test_dimensions_are_not_warnings():
    """블록 사진의 치수(350, 835)는 용접 표기가 아니라 경고를 붙이지 않음"""
    result = run(vision_with([("350", 0.9), ("835", 0.8)]))
    assert [m["meaning"] for m in result["dictionary_matches"]] == ["치수 350mm (용접 표기 아님)", "치수 835mm (용접 표기 아님)"]
    assert result["conflicts"] == []


# ── 셀 형태 (PAC 과제) ──

def test_cell_sides_from_symbol_position():
    """셀 형태 기호를 사진 가운데(가로 1920 → 960) 기준 왼쪽·오른쪽 끝으로 나눔"""
    v = vision_with(symbols=[("scallop", 0.8), ("collar_front", 0.7), ("scallop", 0.9)])
    v["symbols"][0]["bbox"] = [10, 100, 60, 140]
    v["symbols"][1]["bbox"] = [1500, 100, 1560, 140]
    v["symbols"][2]["bbox"] = [1800, 100, 1860, 140]
    result = run(v)
    assert result["cell"] == {"left": ["scallop"], "right": ["collar_front", "scallop"], "ref_ids": ["s1", "s2", "s3"]}


def test_no_cell_symbols():
    assert run()["cell"] is None


def test_cell_from_vlm_symbol_without_position_needs_review(monkeypatch):
    response = {**VLM_EXAMPLE, "symbols": VLM_EXAMPLE["symbols"] + [{"label": "slot", "ref_id": "new1", "bbox": None}]}
    fake_vlm(monkeypatch, response, runs=1)
    result = run()
    assert result["cell"] is None
    assert any(c["type"] == "ambiguous_reading" and "slot" in c["message"] for c in result["conflicts"])


def test_corrected_cell_and_leg_lengths():
    result = run(corrections=[
        {"target": "cell", "value": {"left": ["slit"], "right": []}},
        {"target": "leg_lengths", "value": [{"code": "V", "size_mm": 6, "raw_text": "V6"}]},
    ])
    assert result["cell"] == {"left": ["slit"], "right": [], "ref_ids": []}
    assert result["leg_lengths"] == [{"code": "V", "size_mm": 6, "raw_text": "V6", "meaning": "2F 용접장 각장", "ref_ids": []}]


# ── 작업에 적은 조립 경로 ──

def test_job_assembly_path_used_when_photo_has_no_part():
    """PAC 셀 사진처럼 부재 번호가 없으면 작업을 만들 때 적은 경로를 씀"""
    result = run(vision_with([("FW", 0.9)]), job_assembly_path="A1/L1/M2/S2/P-3")
    assert result["part"] == {"node_id": "P-3", "assembly_path": "A1/L1/M2/S2/P-3", "level": "PART",
                              "found_in_tree": True, "ref_ids": []}
    assert "part_not_in_tree" not in types(result)


def test_job_assembly_path_not_in_tree():
    result = run(vision_with([("FW", 0.9)]), job_assembly_path="Z9/P-9")
    assert result["part"]["assembly_path"] == "Z9/P-9" and result["part"]["found_in_tree"] is False
    assert ("part_not_in_tree", "warning") in [(c["type"], c["severity"]) for c in result["conflicts"]]


def test_part_marking_wins_over_job_path():
    assert run(job_assembly_path="A1/L1/M2/S2/P-3")["part"]["assembly_path"] == "A1/L1/M2/S1/P-1"


def test_thickness_out_of_range():
    result = run(vision_with([("BV", 0.9), ("t=6", 0.9)]))
    assert result["welding_condition"] is None
    assert types(result) == ["dictionary_unmatched", "standard_conflict"]  # t=6은 사전에 없음 (info)


def test_conflicting_joint_types():
    result = run(vision_with([("FW", 0.9), ("BV", 0.6), ("t=10", 0.9)]))
    assert result["welding_condition"]["joint_type"] == "FILLET"
    assert "standard_conflict" in types(result)


# ── 작업자 수정 (corrections) ──

def test_corrected_text_is_used():
    result = run(corrections=[{"target": "t2", "value": "BV", "previous": "FW"}])
    m = next(m for m in result["dictionary_matches"] if m["ref_ids"] == ["t2"])
    assert (m["raw"], m["code"], m["score"]) == ("BV", "BV", 1.0)
    assert result["welding_condition"] is None  # 기준표에 V형 맞대기(BUTT_V) 행이 없음
    assert any(c["type"] == "standard_conflict" and "BUTT_V" in c["message"] for c in result["conflicts"])


def test_corrected_meaning_and_no_conflict():
    result = run(corrections=[{"target": "t3", "value": "t=10", "meaning": "판 두께 10mm (작업자)"}])
    m = next(m for m in result["dictionary_matches"] if m["ref_ids"] == ["t3"])
    assert m["meaning"] == "판 두께 10mm (작업자)"
    assert result["conflicts"] == []


def test_corrected_part_and_welding_condition():
    welding = {**EXPECTED["welding_condition"], "source": "manual"}
    del welding["ref_ids"]
    result = run(corrections=[{"target": "part", "value": "A1/L1/M2/S1/P-2"},
                              {"target": "welding_condition", "value": welding}])
    assert result["part"] == {"node_id": "P-2", "assembly_path": "A1/L1/M2/S1/P-2", "level": "PART",
                              "found_in_tree": True, "ref_ids": []}
    assert result["welding_condition"] == welding


# ── VLM ──

def test_vlm_example(monkeypatch):
    calls = fake_vlm(monkeypatch, VLM_EXAMPLE, runs=3)
    result = run()
    assert len(calls) == 3 and calls[0]["model"] == "claude-opus-5-5" and calls[0]["image"] is None
    assert result["vlm"] == EXPECTED["vlm"]
    t3 = next(m for m in result["dictionary_matches"] if m["ref_ids"] == ["t3"])
    assert (t3["match"], t3["meaning"], t3["score"]) == ("vlm", "판 두께 10mm", 1.0)
    assert [(c["type"], c["severity"], c["ref_ids"]) for c in result["conflicts"]] == [
        (c["type"], c["severity"], c["ref_ids"]) for c in EXPECTED["conflicts"]]


def test_vlm_only_marking_gets_v_id(monkeypatch):
    extra = copy.deepcopy(VLM_EXAMPLE)
    extra["texts"].append({"text": "S-3", "ref_id": "new1", "bbox": [900, 300, 980, 360]})
    extra["meanings"].append({"ref_id": "new1", "meaning": "스티프너 3번"})
    fake_vlm(monkeypatch, extra, runs=1)
    result = run()
    assert result["vlm"]["reading"]["texts"][-1] == {"text": "S-3", "ref_id": "v1", "bbox": [900, 300, 980, 360]}
    assert result["vlm"]["consistency"] is None and result["vlm"]["runs"] == 1
    v1 = next(m for m in result["dictionary_matches"] if m["ref_ids"] == ["v1"])
    assert (v1["match"], v1["meaning"]) == ("vlm", "스티프너 3번")
    assert ("ocr_vlm_mismatch", ["v1"]) in [(c["type"], c["ref_ids"]) for c in result["conflicts"]]


def test_vlm_keeps_previous_v_ids(monkeypatch):
    """다시 돌려도 같은 표기는 이전 revision의 v* 그대로, 새 표기는 비어 있는 다음 번호"""
    response = copy.deepcopy(VLM_EXAMPLE)
    response["texts"] += [{"text": "NEW", "ref_id": "new1", "bbox": None}, {"text": "S-3", "ref_id": "new2", "bbox": None}]
    fake_vlm(monkeypatch, response, runs=1)
    previous = {"texts": [{"text": "S-3", "ref_id": "v1"}], "symbols": []}
    result = run(previous_reading=previous)
    assert [(x["text"], x["ref_id"]) for x in result["vlm"]["reading"]["texts"][3:]] == [("NEW", "v2"), ("S-3", "v1")]


def test_vlm_keeps_corrected_v_id_even_if_not_read(monkeypatch):
    fake_vlm(monkeypatch, VLM_EXAMPLE, runs=1)
    previous = {"texts": [{"text": "S-3", "ref_id": "v1"}], "symbols": []}
    result = run(previous_reading=previous, corrections=[{"target": "v1", "value": "S-3"}])
    assert {"text": "S-3", "ref_id": "v1"} in result["vlm"]["reading"]["texts"]


def test_vlm_consistency_and_mismatch(monkeypatch):
    other = copy.deepcopy(VLM_EXAMPLE)
    other["texts"][1]["text"] = "EW"
    fake_vlm(monkeypatch, VLM_EXAMPLE, other, VLM_EXAMPLE)
    assert run()["vlm"]["consistency"] == 0.67
    fake_vlm(monkeypatch, other, runs=1)
    assert ("ocr_vlm_mismatch", ["t2"]) in [(c["type"], c["ref_ids"]) for c in run()["conflicts"]]


def test_vlm_uses_related_jobs(monkeypatch):
    calls = fake_vlm(monkeypatch, VLM_EXAMPLE, runs=1)
    related = [{"job_id": "job_demo_p2", "assembly_path": "A1/L1/M2/S1/P-2", "interpretation": "필렛 용접"}]
    result = run(related_jobs=related)
    assert result["related_job_ids"] == ["job_demo_p2"] and "job_demo_p2" in calls[0]["prompt"]


def test_previous_vlm_kept_for_corrected_v_id():
    """VLM이 꺼진 채 재해석해도 작업자가 고친 v*가 있으면 이전 VLM 결과를 이어 씀"""
    previous = copy.deepcopy(EXPECTED["vlm"])
    previous["reading"]["texts"].append({"text": "S-3", "ref_id": "v1"})
    ci = {**CONTEXT_INPUT, "previous_reading": previous["reading"], "corrections": [{"target": "v1", "value": "S-3"}]}
    result = check(VISION, interpret(VISION, ci, previous_vlm=previous))
    assert result["vlm"] == previous
    assert any(m["ref_ids"] == ["v1"] for m in result["dictionary_matches"])
    assert interpret(VISION, CONTEXT_INPUT, previous_vlm=previous)["vlm"] is None  # 고친 v*가 없으면 이어 쓰지 않음


def test_vlm_failure_falls_back(monkeypatch):
    """추론이 모두 실패하면 VLM 없이 해석하고, 실패 이유를 vlm_error에 남김 (조용히 묻히지 않게)"""
    def broken(*args):
        raise RuntimeError("API 키 없음")

    monkeypatch.setenv("VLM_PROVIDER", "claude")
    monkeypatch.setitem(vlm_module.PROVIDERS, "claude", broken)
    result = run()
    assert result["vlm"] is None
    assert "API 키 없음" in result["vlm_error"] and result["vlm_error"].startswith("claude(")


def test_no_vlm_error_when_off_or_ok(monkeypatch):
    assert "vlm_error" not in run()
    fake_vlm(monkeypatch, VLM_EXAMPLE, runs=1)
    assert "vlm_error" not in run()


def _photo(width=1920, height=1080):
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    return np.full((height, width, 3), 128, np.uint8)


def test_vlm_reading_used_when_it_saw_the_photo(monkeypatch):
    """사진을 본 VLM이 확률 낮은 1단계 읽기를 다르게 읽으면 VLM 값으로 해석 (PAC 손글씨 '—4' → 'F4.5')"""
    response = {"interpretation": "3F 각장 4.5mm", "texts": [{"text": "F4.5", "ref_id": "t1", "bbox": None}],
                "symbols": [], "meanings": []}
    fake_vlm(monkeypatch, response, runs=1)
    vision = vision_with([("—4", 0.57)])
    result = check(vision, interpret(vision, CONTEXT_INPUT, image=_photo()))
    (m,) = result["dictionary_matches"]
    assert (m["raw"], m["code"], m["meaning"]) == ("F4.5", "F", "3F 용접장 각장 4.5mm")
    assert result["leg_lengths"][0]["size_mm"] == 4.5
    assert result["vlm"]["image_attached"] is True
    assert result["vlm"]["reading"]["texts"] == [{"text": "F4.5", "ref_id": "t1", "used": True}]
    assert [(c["type"], c["severity"]) for c in result["conflicts"] if c["type"] == "ocr_vlm_mismatch"] == [
        ("ocr_vlm_mismatch", "info")]


def test_vlm_reading_not_used_without_photo(monkeypatch):
    other = copy.deepcopy(VLM_EXAMPLE)
    other["texts"][1]["text"] = "EW"
    fake_vlm(monkeypatch, other, runs=1)
    result = run()
    assert next(m for m in result["dictionary_matches"] if m["ref_ids"] == ["t2"])["raw"] == "FW"
    assert not any(x.get("used") for x in result["vlm"]["reading"]["texts"])


def test_confident_ocr_kept_over_vlm(monkeypatch):
    """1단계가 확실하게(≥ 90%) 사전에 있는 값을 읽었으면 VLM이 달라도 1단계 값 + 경고"""
    response = {"interpretation": "", "texts": [{"text": "BV", "ref_id": "t1", "bbox": None}], "symbols": [], "meanings": []}
    fake_vlm(monkeypatch, response, runs=1)
    vision = vision_with([("FW", 0.97)])
    result = check(vision, interpret(vision, CONTEXT_INPUT, image=_photo()))
    assert result["dictionary_matches"][0]["code"] == "FW"
    assert ("ocr_vlm_mismatch", "warning") in [(c["type"], c["severity"]) for c in result["conflicts"]]


def test_vlm_only_markings_grouped_when_ocr_found_nothing(monkeypatch):
    """1단계가 아무것도 못 읽은 손글씨 사진은 VLM 표기마다 경고를 붙이지 않고 info 하나로"""
    response = {"interpretation": "", "texts": [{"text": "F5.0", "ref_id": "new1", "bbox": None},
                                                {"text": "V5", "ref_id": "new2", "bbox": None}],
                "symbols": [{"label": "→", "ref_id": "new3", "bbox": None}], "meanings": []}
    fake_vlm(monkeypatch, response, runs=1)
    vision = vision_with()
    result = check(vision, interpret(vision, CONTEXT_INPUT))
    mismatches = [c for c in result["conflicts"] if c["type"] == "ocr_vlm_mismatch"]
    assert [(c["severity"], c["ref_ids"]) for c in mismatches] == [("info", ["v1", "v2", "v3"])]
    assert not [c for c in result["conflicts"] if c["severity"] != "info"]
    assert [leg["raw_text"] for leg in result["leg_lengths"]] == ["F5.0", "V5"]


def test_vlm_bbox_back_to_original_coords(monkeypatch):
    """원본보다 크게(작은 사진) 또는 작게(큰 사진) 보낸 사진의 bbox를 원본 좌표로 되돌림"""
    response = {"interpretation": "", "texts": [{"text": "S-3", "ref_id": "new1", "bbox": [512, 256, 1024, 512]}],
                "symbols": [], "meanings": []}
    calls = fake_vlm(monkeypatch, response, runs=1)
    vision = {**vision_with(), "image_size": {"width": 343, "height": 200}}
    result = check(vision, interpret(vision, CONTEXT_INPUT, image=_photo(343, 200)))
    assert '"width": 1024' in calls[0]["prompt"]  # 긴 변 343px → 1024px로 키워 보냄
    x1, y1, x2, y2 = result["vlm"]["reading"]["texts"][0]["bbox"]
    assert (x1, x2) == (172, 343) and (y1, y2) == (86, 172)  # 세로 200 / 597


def test_vlm_consistency_ignores_v_id_order(monkeypatch):
    """1단계가 놓친 표기를 추론마다 다른 순서로 읽어도(new1 ↔ new2) 같은 읽기로 셈"""
    first = {"interpretation": "", "texts": [{"text": "F5.0", "ref_id": "new1", "bbox": None},
                                             {"text": "V5", "ref_id": "new2", "bbox": None}], "symbols": [], "meanings": []}
    second = {**first, "texts": list(reversed(first["texts"]))}
    fake_vlm(monkeypatch, first, second, first)
    assert run(vision_with())["vlm"]["consistency"] == 1.0


def test_unknown_vlm_symbol_is_not_a_warning(monkeypatch):
    response = {"interpretation": "", "texts": [], "symbols": [{"label": "unknown", "ref_id": "new1", "bbox": None}], "meanings": []}
    fake_vlm(monkeypatch, response, runs=1)
    result = run(vision_with())
    assert [c["severity"] for c in result["conflicts"]] == ["info", "info"]


def test_vlm_runs_in_parallel(monkeypatch):
    """VLM_RUNS번 추론을 동시에 보냄 (차례로 보내면 Claude 20초 × 3)"""
    barrier = threading.Barrier(3, timeout=5)

    def generate(system, prompt, image, model):
        barrier.wait()  # 3개가 동시에 들어와야 통과
        return json.dumps(VLM_EXAMPLE, ensure_ascii=False), None

    monkeypatch.setenv("VLM_PROVIDER", "claude")
    monkeypatch.setenv("VLM_RUNS", "3")
    monkeypatch.setitem(vlm_module.PROVIDERS, "claude", generate)
    assert run()["vlm"]["consistency"] == 1.0


def test_vlm_image_bytes(monkeypatch):
    calls = fake_vlm(monkeypatch, VLM_EXAMPLE, runs=1)
    interpret(VISION, CONTEXT_INPUT, image=b"\x89PNG....")
    assert calls[0]["image"] == (b"\x89PNG....", "image/png")


def test_unknown_provider(monkeypatch):
    monkeypatch.setenv("VLM_PROVIDER", "llava")
    with pytest.raises(ValueError):
        interpret(VISION, CONTEXT_INPUT)


# ── VLM 에 보내는 사진 크기 (휴대폰 원본은 Claude 10MB 한도를 넘음) ──

def test_vlm_image_tiny_enlarged():
    """운영측 손글씨 예시(343px)처럼 작은 사진은 VLM이 숫자를 틀려서 긴 변 1024px PNG로 키워 보냄"""
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")

    from db_context_interpreter.vlm import UPSCALE_SIDE, load_image

    data, media = load_image(np.full((200, 343, 3), 120, np.uint8), {"preprocess": {}})
    assert media == "image/png"
    assert cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR).shape[:2] == (597, UPSCALE_SIDE)


def test_vlm_image_small_kept_as_is():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")

    from db_context_interpreter.vlm import load_image

    image = np.full((480, 640, 3), 120, np.uint8)
    data, media = load_image(image, {"preprocess": {}})
    assert media == "image/png"
    assert cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR).shape == (480, 640, 3)


def test_vlm_image_large_shrunk_to_jpeg():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")

    from db_context_interpreter.vlm import MAX_IMAGE_BYTES, MAX_IMAGE_SIDE, load_image

    rng = np.random.default_rng(0)
    image = rng.integers(0, 256, (3000, 4000, 3), dtype=np.uint8)  # 노이즈라 PNG 가 매우 큼
    data, media = load_image(image, {"preprocess": {}})
    assert media == "image/jpeg"
    assert len(data) <= MAX_IMAGE_BYTES * 2  # 원래 수십 MB → 몇 MB
    shrunk = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    assert max(shrunk.shape[:2]) == MAX_IMAGE_SIDE
    assert shrunk.shape[1] / shrunk.shape[0] == pytest.approx(4000 / 3000, rel=0.01)  # 비율 유지


def test_vlm_runs_pick_consensus_per_marking(monkeypatch):
    """세 번 추론이 화살표 등 다른 표기 때문에 모두 다르더라도, 각장은 다수(F5.5)를 고름 — 일관성은 전체 일치 기준(1/3)"""
    def response(leg, extra):
        return {"interpretation": f"각장 {leg}", "texts": [{"text": leg, "ref_id": "new1", "bbox": None}],
                "symbols": [{"label": "→", "ref_id": "new2", "bbox": None}] * extra, "meanings": []}
    fake_vlm(monkeypatch, response("F7.5", 0), response("F5.5", 1), response("F5.5", 0))
    result = run(vision_with([]))
    assert [x["text"] for x in result["vlm"]["reading"]["texts"]] == ["F5.5"]
    assert result["vlm"]["consistency"] == 0.33


def _vlm_reads(*texts: str) -> dict:
    return {"interpretation": "", "texts": [{"text": t, "ref_id": f"t{i}", "bbox": None} for i, t in enumerate(texts, 1)],
            "symbols": [], "meanings": []}


def test_leg_read_only_by_ocr_is_dropped_when_vlm_saw_photo(monkeypatch):
    """각장 위주로 학습한 인식기가 치수 418을 F11.8로 지어냄 → 사진을 본 VLM이 읽지 않은 각장은 빼고 작업자 확인"""
    fake_vlm(monkeypatch, _vlm_reads("418", "F5.5"), runs=1)
    vision = vision_with([("F11.8", 0.95), ("F5.5", 0.95)])
    result = check(vision, interpret(vision, CONTEXT_INPUT, image=_photo()))
    assert [leg["raw_text"] for leg in result["leg_lengths"]] == ["F5.5"]
    assert ("ocr_vlm_mismatch", "warning", ["t1"]) in [(c["type"], c["severity"], c["ref_ids"]) for c in result["conflicts"]
                                                        if "F11.8" in c["message"]]


def test_leg_kept_when_vlm_reads_it_on_the_same_line(monkeypatch):
    """VLM이 한 줄로 읽어도(F5.5 V6) 값이 같으면 같은 각장"""
    fake_vlm(monkeypatch, _vlm_reads("F5.5 V6"), runs=1)
    vision = vision_with([("F5.5 V6.0", 0.95)])
    result = check(vision, interpret(vision, CONTEXT_INPUT, image=_photo()))
    assert [leg["raw_text"] for leg in result["leg_lengths"]] == ["F5.5", "V6.0"]


def test_leg_kept_without_photo_for_vlm(monkeypatch):
    """VLM이 사진을 보지 못했으면 확인할 길이 없어 1단계 각장을 그대로 씀"""
    fake_vlm(monkeypatch, _vlm_reads("418"), runs=1)
    result = run(vision_with([("F11.8", 0.95)]))
    assert [leg["raw_text"] for leg in result["leg_lengths"]] == ["F11.8"]


def test_leg_from_ocr_candidate_is_dropped_when_vlm_read_otherwise(monkeypatch):
    """VLM 읽기(Angle)를 썼는데 사전에 안 맞아 1단계 값(F18.0)이 후보로 대조돼도 VLM이 읽지 않은 각장이면 뺌"""
    fake_vlm(monkeypatch, _vlm_reads("Angle"), runs=1)
    vision = vision_with([("F18.0", 0.6)])
    result = check(vision, interpret(vision, CONTEXT_INPUT, image=_photo()))
    assert result["leg_lengths"] == []
