"""VLM 프롬프트와 응답 형식 — provider와 상관없이 같은 JSON을 받음"""
import json

SYSTEM = """당신은 조선소 선박 블록의 부재 표기(각인·스텐실·마커 손글씨·라벨)를 해석하는 용접 전문가입니다.
사진(있으면)과 1단계 OCR/기호 인식 결과를 보고, 워크스페이스 문자/기호 사전 · 프로젝트 조립 트리 · 표준 용접 기준과 대조해 표기의 의미를 해석합니다.

규칙:
- 사진에서 직접 읽은 글자·기호를 texts·symbols에 모두 적습니다. 1단계 결과에 대응하면 그 ref_id(t1, s1 …)를, 1단계가 놓친 표기면 new1, new2 …를 씁니다.
- 사진이 없으면 1단계 결과를 그대로 읽은 것으로 보고 적되, 맥락상 틀린 읽기(예: 후보 중 사전에 있는 것)가 분명하면 고친 값을 적습니다.
- 작업자 수정(corrections)은 확정된 값이므로 그대로 따릅니다.
- 기호 label은 사전의 code를 씁니다. 사전에 없는 기호는 "unknown".
- meanings에는 사전에 없는 표기(판 두께 t=10 등)만 의미를 적습니다. 사전에 있는 표기는 적지 않습니다.
- interpretation은 한국어 한두 문장으로 부재·조립 경로, 이음 형태, 판 두께, 각장, 현장 용접 여부 등을 요약합니다. 보이지 않는 값은 지어내지 않습니다.
- bbox는 원본 이미지 픽셀 좌표 [x1, y1, x2, y2]이고 모르면 null입니다.
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


def build_prompt(vision_result: dict, context_input: dict, has_image: bool) -> str:
    """사진 한 장의 해석 요청 (사진은 provider가 따로 붙임)"""
    recognized = [
        {"ref_id": t["id"], "kind": "text", "value": t["text"], "prob": t["prob"], "bbox": t["bbox"],
         "candidates": [c["text"] for c in t.get("candidates", [])]}
        for t in vision_result["texts"]
    ] + [
        {"ref_id": s["id"], "kind": "symbol", "value": s["label"], "prob": s["prob"], "bbox": s["bbox"],
         "candidates": [c["label"] for c in s.get("candidates", [])]}
        for s in vision_result["symbols"]
    ]
    data = {
        "image": {"attached": has_image, **vision_result["image_size"]},
        "recognized": recognized,
        "corrections": [{k: c[k] for k in ("target", "value", "meaning") if k in c} for c in context_input["corrections"]],
        "user_context": context_input["user_context"],
        "dictionary": [{k: e[k] for k in ("code", "kind", "meaning", "aliases", "welding_joint_type")} for e in context_input["symbols"]],
        "assembly_tree": [n["path"] for n in context_input["assembly_tree"]],
        "welding_standards": [
            f"{s['joint_type']} {s['thickness_min_mm']:g}~{s['thickness_max_mm']:g}mm {s['process']} {s['position']}"
            for s in context_input["welding_standards"]
        ],
        "related_jobs": context_input["related_jobs"],
    }
    return (
        "다음 표기 정보를 해석하세요.\n\n"
        f"```json\n{json.dumps(data, ensure_ascii=False, indent=1)}\n```\n\n"
        "응답 JSON 형식:\n"
        f"```json\n{json.dumps(RESPONSE_SCHEMA, ensure_ascii=False)}\n```"
    )


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
