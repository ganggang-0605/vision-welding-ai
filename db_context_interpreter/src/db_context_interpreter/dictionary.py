"""b. 문자/기호 DB: 워크스페이스 사전 대조"""


def match_dictionary(vision_result: dict, context_input: dict, vlm: dict | None) -> list[dict]:
    """1단계 글자·기호(작업자가 고친 값 우선)를 context_input["symbols"]의 code·aliases와 대조 → DictionaryMatch 목록.

    match: exact 그대로 일치 / alias 별칭 일치 / candidate 1단계 후보 중 하나가 일치 / fuzzy 유사 일치 /
           vlm 사전에 없지만 VLM이 해석 / none 해석 못 함
    """
    # TODO
    return []
