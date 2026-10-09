"""c. 조립 경로 DB: 블록 → 대조립 → 중조립 → 소조립 → 부재"""


def find_part(vision_result: dict, context_input: dict) -> dict:
    """부재 번호로 보이는 표기를 context_input["assembly_tree"]에서 찾아 Part를 만듦.
    작업자가 part를 고쳤으면(corrections) 그 조립 경로를 씀. 못 찾으면 아래 빈 Part"""
    # TODO
    return {"node_id": None, "assembly_path": None, "level": None, "found_in_tree": False, "ref_ids": []}
