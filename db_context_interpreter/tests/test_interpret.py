import copy
import json

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
    """VLM_PROVIDER=claude로 켜되 실제 API 대신 responses를 차례로 돌려줌 (마지막 것을 반복)"""
    calls = []

    def generate(system, prompt, image, model):
        calls.append({"prompt": prompt, "image": image, "model": model})
        return json.dumps(responses[min(len(calls), len(responses)) - 1], ensure_ascii=False), None

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
    assert result["welding_condition"] is None  # FILLET이지만 판 두께가 없어 기준 행(6~12 · 12~20)을 못 고름


def test_candidate_match():
    result = run(vision_with([("EW", 0.5, [("FW", 0.4)])]))
    (m,) = result["dictionary_matches"]
    assert (m["raw"], m["code"], m["match"], m["score"]) == ("FW", "FW", "candidate", 0.4)


def test_ambiguous_candidates():
    """후보끼리 확률이 붙어 있고 사전 해석이 달라지면 ambiguous_reading"""
    result = run(vision_with([("FW", 0.45, [("BV", 0.4)])]))
    assert result["dictionary_matches"][0]["code"] == "FW"
    assert "ambiguous_reading" in types(result)


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


# ── 조립 경로 ──

def test_part_without_dash_and_deepest_node():
    result = run(vision_with([("S2", 0.9), ("P3", 0.8)]))
    assert result["part"] == {"node_id": "P-3", "assembly_path": "A1/L1/M2/S2/P-3", "level": "PART",
                              "found_in_tree": True, "ref_ids": ["t1", "t2"]}


def test_part_on_different_branches_is_ambiguous():
    result = run(vision_with([("P-1", 0.9), ("P-3", 0.8)]))
    assert result["part"]["node_id"] == "P-1"
    assert "ambiguous_reading" in types(result)


def test_part_not_in_tree():
    result = run(vision_with([("P-9", 0.9)]))
    assert result["part"] == {"node_id": "P-9", "assembly_path": None, "level": None, "found_in_tree": False, "ref_ids": ["t1"]}
    assert types(result) == ["part_not_in_tree"]


def test_no_part():
    assert run(vision_with([("FW", 0.9)]))["part"]["assembly_path"] is None


# ── 용접 기준 ──

@pytest.mark.parametrize("thickness, current", [("t=8", "220-260"), ("T12", "250-290"), ("20t", "250-290")])
def test_standard_row_by_thickness(thickness, current):
    result = run(vision_with([("FW", 0.9), (thickness, 0.9)]))
    assert result["welding_condition"]["current_a"] == current


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
    assert result["welding_condition"]["joint_type"] == "BUTT_V"


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


def test_vlm_failure_falls_back(monkeypatch):
    def broken(*args):
        raise RuntimeError("API 키 없음")

    monkeypatch.setenv("VLM_PROVIDER", "claude")
    monkeypatch.setitem(vlm_module.PROVIDERS, "claude", broken)
    assert run()["vlm"] is None


def test_vlm_image_bytes(monkeypatch):
    calls = fake_vlm(monkeypatch, VLM_EXAMPLE, runs=1)
    interpret(VISION, CONTEXT_INPUT, image=b"\x89PNG....")
    assert calls[0]["image"] == (b"\x89PNG....", "image/png")


def test_unknown_provider(monkeypatch):
    monkeypatch.setenv("VLM_PROVIDER", "llava")
    with pytest.raises(ValueError):
        interpret(VISION, CONTEXT_INPUT)
