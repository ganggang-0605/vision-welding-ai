"""인식 결과 ID (t*, s*, v*)"""


def is_ref(target: str) -> bool:
    """작업자 확인 대상이 인식 결과 ID(t*, s*, v*)인지"""
    return target[0] in "tsv" and target[1:].isdigit()


def vlm_only(context: dict) -> list[dict]:
    """1단계가 놓치고 VLM만 읽은 표기 (ref_id가 v*)"""
    if not context["vlm"]:
        return []
    reading = context["vlm"]["reading"]
    return [x for x in reading["texts"] + reading["symbols"] if x["ref_id"][0] == "v"]
