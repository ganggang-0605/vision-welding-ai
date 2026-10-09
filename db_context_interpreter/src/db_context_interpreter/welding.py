"""a. 용접 기준 DB: 표준 용접 기준표 대조"""


def find_welding_condition(matches: list[dict], vision_result: dict, context_input: dict) -> dict | None:
    """사전 항목의 welding_joint_type + 판 두께 표기(예: t=10)로 context_input["welding_standards"]의 행을 찾아
    WeldingCondition을 만듦 (standard_matched, source="standard_db", ref_ids = 근거 표기). 판별 못 하면 None"""
    # TODO
    return None
