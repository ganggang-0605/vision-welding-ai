"""[2단계] 진입점: 사전 대조 → 부재·조립 경로 → 용접 조건 → VLM 해석 → DB 불일치"""
from db_context_interpreter.assembly import find_part
from db_context_interpreter.dictionary import match_dictionary
from db_context_interpreter.vlm import interpret_with_vlm
from db_context_interpreter.welding import find_welding_condition


def interpret(vision_result: dict, context_input: dict) -> dict:
    """VisionResult + ContextInput → ContextResult. 작업자 확인(재해석·직접 해석) 때도 이 함수부터 다시 돌림"""
    vlm = interpret_with_vlm(vision_result, context_input)
    matches = match_dictionary(vision_result, context_input, vlm)
    part = find_part(vision_result, context_input)
    welding_condition = find_welding_condition(matches, vision_result, context_input)
    return {
        "user_context": context_input["user_context"],
        "related_job_ids": [],  # TODO: related_jobs를 맥락으로 쓰면 그 job_id
        "dictionary_matches": matches,
        "part": part,
        "welding_condition": welding_condition,
        "conflicts": find_conflicts(matches, part, welding_condition, vlm),
        "vlm": vlm,
    }


def find_conflicts(matches: list[dict], part: dict, welding_condition: dict | None, vlm: dict | None) -> list[dict]:
    """DB 불일치 항목 (Conflict). type은 3단계 needs_review.reason과 같은 이름"""
    # TODO: dictionary_unmatched(match none·vlm) · part_not_in_tree · standard_conflict · ocr_vlm_mismatch · ambiguous_reading
    return []
