from vw_shared import load_example, schema_errors, semantic_errors

from db_context_interpreter import interpret

VISION = load_example("vision_result.example.json")
CONTEXT_INPUT = load_example("context_input.example.json")


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
