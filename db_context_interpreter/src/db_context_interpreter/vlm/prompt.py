"""VLM 프롬프트와 응답 형식 — provider와 상관없이 같은 JSON을 받음"""
import json

SYSTEM = """당신은 조선소 선박 블록의 부재 표기(각인·스텐실·마커 손글씨·라벨)를 해석하는 용접 전문가입니다.
사진(있으면)과 1단계 OCR/기호 인식 결과를 보고, 워크스페이스 문자/기호 사전 · 프로젝트 조립 트리 · 표준 용접 기준과 대조해 표기의 의미를 해석합니다.

규칙:
- 사진에서 직접 읽은 글자·기호를 texts·symbols에 모두 적습니다. 1단계 결과에 대응하면 그 ref_id(t1, s1 …)를, 1단계가 놓친 표기면 new1, new2 …를 씁니다.
- 사진이 없으면 1단계 결과를 그대로 읽은 것으로 보고 적되, 맥락상 틀린 읽기(예: 후보 중 사전에 있는 것)가 분명하면 고친 값을 적습니다.
- 작업자 수정(corrections)은 확정된 값이므로 그대로 따릅니다. 다만 texts·symbols에는 사진에서 직접 보이는 것만 적고, corrections의 값(셀 형태·각장 등)을 옮겨 적지 않습니다.
- 기호 label은 사전의 code를 씁니다. 사전에 없는 기호는 "unknown".
- meanings에는 사전에 없는 표기(판 두께 t=10 등)만 의미를 적습니다. 사전에 있는 표기는 적지 않습니다.
- 셀 끝 절단부(론지 관통부)가 보이면 symbols에 사전 code(slit, slot, collar_front, collar_back, scallop)로 적고 bbox를 꼭 적습니다. 왼쪽·오른쪽 끝을 가르는 데 씁니다.
- 수기 각장(F·V·S 뒤의 숫자)은 보통 3~13mm입니다. 소수점이 흐려 보여도 "F55"가 아니라 "F5.5"처럼 읽고, 5와 6 · 4처럼 헷갈리는 숫자는 획을 다시 확인합니다.
- 치수(350, 835 같은 mm 숫자)는 texts에 적되 용접 표기로 해석하지 않습니다.
- interpretation은 한국어 한두 문장으로 부재·조립 경로, 이음 형태, 판 두께, 각장, 셀 형태, 현장 용접 여부 등을 요약합니다. 보이지 않는 값은 지어내지 않습니다.
- bbox는 첨부한 사진의 픽셀 좌표 [x1, y1, x2, y2] (image.width · image.height 기준)이고 모르면 null입니다. recognized의 bbox도 같은 좌표입니다.
- 반드시 지정한 JSON 형식으로만 답합니다."""

BBOX = {"anyOf": [{"type": "array", "items": {"type": "number"}}, {"type": "null"}]}
RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["interpretation", "texts", "symbols", "meanings"],
    "properties": {
        "interpretation": {"type": "string"},
        "texts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["text", "ref_id", "bbox"],
            "properties": {"text": {"type": "string"}, "ref_id": {"type": "string"}, "bbox": BBOX},
        }},
        "symbols": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["label", "ref_id", "bbox"],
            "properties": {"label": {"type": "string"}, "ref_id": {"type": "string"}, "bbox": BBOX},
        }},
        "meanings": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["ref_id", "meaning"],
            "properties": {"ref_id": {"type": "string"}, "meaning": {"type": "string"}},
        }},
    },
}


def build_prompt(vision_result: dict, context_input: dict, has_image: bool, sent_size: dict | None = None) -> str:
    """사진 한 장의 해석 요청 (사진은 provider가 따로 붙임). sent_size: 보낸 사진 크기 — 원본과 다르면 1단계 bbox를 그 크기로 바꿈"""
    size = sent_size or vision_result["image_size"]
    sx, sy = size["width"] / vision_result["image_size"]["width"], size["height"] / vision_result["image_size"]["height"]

    def box(bbox: list) -> list:
        return bbox if (sx, sy) == (1.0, 1.0) else [round(bbox[0] * sx), round(bbox[1] * sy), round(bbox[2] * sx), round(bbox[3] * sy)]

    recognized = [
        {"ref_id": t["id"], "kind": "text", "value": t["text"], "prob": t["prob"], "bbox": box(t["bbox"]),
         "candidates": [c["text"] for c in t.get("candidates", [])]}
        for t in vision_result["texts"]
    ] + [
        {"ref_id": s["id"], "kind": "symbol", "value": s["label"], "prob": s["prob"], "bbox": box(s["bbox"]),
         "candidates": [c["label"] for c in s.get("candidates", [])]}
        for s in vision_result["symbols"]
    ]
    data = {
        "image": {"attached": has_image, **size},
        "recognized": recognized,
        "corrections": [{k: c[k] for k in ("target", "value", "meaning") if k in c} for c in context_input["corrections"]],
        "user_context": context_input["user_context"],
        "dictionary": [{k: e[k] for k in ("code", "kind", "meaning", "aliases", "welding_joint_type")} for e in context_input["symbols"]],
        "assembly_tree": [n["path"] for n in context_input["assembly_tree"]],
        "welding_standards": [standard_line(s) for s in context_input["welding_standards"]],
        "related_jobs": context_input["related_jobs"],
    }
    return (
        "다음 표기 정보를 해석하세요.\n\n"
        f"```json\n{json.dumps(data, ensure_ascii=False, indent=1)}\n```\n\n"
        "응답 JSON 형식:\n"
        f"```json\n{json.dumps(RESPONSE_SCHEMA, ensure_ascii=False)}\n```"
    )


def standard_line(s: dict) -> str:
    """기준표 한 행 요약 (예: FILLET 판 두께 6mm 각장 5mm GMAW 2F)"""
    parts = [s["joint_type"]]
    if s["thickness_min_mm"] is not None:
        parts.append(f"판 두께 {span(s['thickness_min_mm'], s['thickness_max_mm'])}mm")
    if s.get("leg_min_mm") is not None:
        parts.append(f"각장 {span(s['leg_min_mm'], s['leg_max_mm'])}mm")
    return " ".join(parts + [s["process"], s["position"]])


def span(low: float, high: float) -> str:
    return f"{low:g}" if low == high else f"{low:g}~{high:g}"


def parse_response(text: str) -> dict:
    """모델 출력 → 응답 dict. 코드 블록으로 감싸 보낸 경우도 받음. 형식이 틀리면 ValueError"""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("interpretation"), str):
        raise ValueError("VLM 응답에 interpretation이 없음")
    for key in ("texts", "symbols", "meanings"):
        if not isinstance(data.get(key, []), list):
            raise ValueError(f"VLM 응답의 {key}가 목록이 아님")
    return data
