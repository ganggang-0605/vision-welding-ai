"""파이프라인 스키마 점검: 예시가 스키마에 맞는지, 단계 사이 연결이 맞는지, 팀원 API 계약(backend/app/schemas.py)과 맞는지 확인

사용: backend/.venv/bin/python shared/validate.py   (jsonschema, pydantic 필요)
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import get_args

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

SHARED = Path(__file__).resolve().parent
ROOT = SHARED.parent
SCHEMAS = SHARED / "schemas"
EXAMPLES = SHARED / "examples"
SEED = ROOT / "data" / "seed"
BASE = "https://vision-welding-ai.local/shared/schemas/"

sys.path.insert(0, str(ROOT / "backend"))
from app import schemas as api  # noqa: E402  팀원 API 계약

EXAMPLE_SCHEMAS = {
    "vision_result.example.json": "vision_result.schema.json",
    "context_result.example.json": "context_result.schema.json",
    "confidence_report.example.json": "confidence_report.schema.json",
    "analysis.example.json": "analysis.schema.json",
    "analysis_revision2.example.json": "analysis.schema.json",
}


def load_registry() -> Registry:
    resources = []
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["$id"] == BASE + path.name, f"{path.name}: $id가 파일 이름과 다름"
        Draft202012Validator.check_schema(schema)
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources)


def schema_errors(instance, ref: str, registry: Registry) -> list[str]:
    validator = Draft202012Validator({"$ref": BASE + ref}, registry=registry, format_checker=FormatChecker())
    return [
        f"{'/'.join(map(str, e.absolute_path)) or '(최상위)'}: {e.message}"
        for e in validator.iter_errors(instance)
    ]


def semantic_errors(analysis: dict) -> list[str]:
    """스키마로는 못 거르는 Analysis 안의 단계 사이 규칙. 백엔드에서도 그대로 가져다 쓸 수 있음"""
    errors = []
    vision, context, confidence = analysis["vision"], analysis["context"], analysis.get("confidence")
    corrections = analysis.get("corrections", [])
    text_ids = [t["id"] for t in vision["texts"]]
    symbol_ids = [s["id"] for s in vision["symbols"]]
    known = set(text_ids) | set(symbol_ids)
    if len(known) != len(text_ids) + len(symbol_ids):
        errors.append("vision: 인식 결과 id가 중복됨")
    vlm_ids = [x["ref_id"] for x in vlm_only(context)]
    if len(set(vlm_ids)) != len(vlm_ids):
        errors.append("context.vlm.reading: v* id가 중복됨")
    known |= set(vlm_ids)

    for t in vision["texts"]:
        if "char_probs" in t and len(t["char_probs"]) != len(t["text"]):
            errors.append(f"vision {t['id']}: char_probs 개수({len(t['char_probs'])})가 글자 수({len(t['text'])})와 다름")
        if t.get("candidates") and t["candidates"][0]["text"] != t["text"]:
            errors.append(f"vision {t['id']}: candidates 첫 번째가 text와 다름")

    refs = [r for m in context["dictionary_matches"] for r in m["ref_ids"]]
    refs += context["part"]["ref_ids"]
    refs += (context["welding_condition"] or {}).get("ref_ids", [])
    refs += [r for c in context["conflicts"] for r in c["ref_ids"]]
    if context["vlm"]:
        reading = context["vlm"]["reading"]
        refs += [x["ref_id"] for x in reading["texts"] if x["ref_id"][0] == "t"]
        refs += [x["ref_id"] for x in reading["symbols"] if x["ref_id"][0] == "s"]
    refs += [c["target"] for c in corrections if is_ref(c["target"])]
    if confidence:
        refs += [r for e in confidence["evidence"] for r in e.get("ref_ids", [])]
        refs += [n["target"] for n in confidence["needs_review"] if is_ref(n["target"])]
        expected = min(confidence["visual"], confidence["db_consistency"], confidence["vlm_reasoning"])
        if confidence["overall"] != expected:
            errors.append(f"confidence: overall({confidence['overall']})은 세 신뢰도의 최솟값({expected})이어야 함")
        fields = to_job_fields(analysis)
        missing = [k for k in ("assembly_path", "welding_condition") if fields[k] is None]
        if confidence["passed"] != (confidence["overall"] >= confidence["threshold"] and not missing):
            errors.append(f"confidence: passed는 overall ≥ threshold이고 필수 값이 모두 있을 때만 true (빠진 값: {missing})")
        targets = {n["target"] for n in confidence["needs_review"]}
        for key, target in (("assembly_path", "part"), ("welding_condition", "welding_condition")):
            if key in missing and target not in targets:
                errors.append(f"confidence: {key}가 없는데 needs_review에 '{target}' 항목이 없음")
        corrected = {c["target"] for c in corrections}
        for n in confidence["needs_review"]:
            if n["target"] in corrected:
                errors.append(f"confidence: 작업자가 이미 고친 '{n['target']}'가 needs_review에 남아 있음")

    for r in sorted(set(refs) - known):
        errors.append(f"'{r}'를 참조하지만 인식 결과(vision, vlm.reading의 v*)에 없음")
    if (analysis.get("revision", 1) > 1) != bool(corrections or context.get("user_context")):
        errors.append("revision 2 이상은 작업자 확인(corrections 또는 user_context)으로만 생김")
    return errors


def is_ref(target: str) -> bool:
    """작업자 확인 대상이 인식 결과 ID(t*, s*, v*)인지"""
    return target[0] in "tsv" and target[1:].isdigit()


def vlm_only(context: dict) -> list[dict]:
    """1단계가 놓치고 VLM만 읽은 표기 (ref_id가 v*)"""
    if not context["vlm"]:
        return []
    reading = context["vlm"]["reading"]
    return [x for x in reading["texts"] + reading["symbols"] if x["ref_id"][0] == "v"]


def latest_analysis(analyses: list[dict]) -> dict:
    """작업 하나의 Analysis 여러 개(사진 여러 장 · revision 여러 개) 중 Job에 반영할 것 = 가장 최근 created_at"""
    return max(analyses, key=lambda a: datetime.fromisoformat(a["created_at"]))


def reading_order(vision: dict, context: dict, corrected: dict[str, str]) -> list[str]:
    """글자·기호를 줄 단위로 묶어 왼→오른, 위→아래 순서로 (작업자가 고친 값 반영). 위치를 모르는 v* 표기는 맨 뒤"""
    items = [(d["bbox"], d["id"], d.get("text") or d.get("label")) for d in vision["texts"] + vision["symbols"]]
    items += [(x["bbox"], x["ref_id"], x.get("text") or x.get("label")) for x in vlm_only(context) if "bbox" in x]
    no_bbox = [corrected.get(x["ref_id"], x.get("text") or x.get("label")) for x in vlm_only(context) if "bbox" not in x]
    items = [(bbox, corrected.get(ref, value)) for bbox, ref, value in items]
    items.sort(key=lambda it: (it[0][1] + it[0][3]) / 2)
    lines: list[list] = []
    for bbox, value in items:
        center = (bbox[1] + bbox[3]) / 2
        if lines and abs(center - lines[-1][0]) <= (lines[-1][1] / 2):
            lines[-1][2].append((bbox[0], value))
        else:
            lines.append([center, bbox[3] - bbox[1], [(bbox[0], value)]])
    return [value for _, _, line in lines for _, value in sorted(line)] + no_bbox


def to_job_fields(analysis: dict) -> dict:
    """Analysis → 팀원 Job(backend/app/schemas.py)의 해석 결과 필드. 백엔드 analyze·review에서 가져다 쓸 수 있음"""
    vision, context, confidence = analysis["vision"], analysis["context"], analysis["confidence"]
    corrections = {c["target"]: c["value"] for c in analysis.get("corrections", [])}
    meanings = {c["target"]: c["meaning"] for c in analysis.get("corrections", []) if "meaning" in c}
    texts = {c: v for c, v in corrections.items() if is_ref(c)}
    wc = corrections.get("welding_condition") or context["welding_condition"]
    vlm = context["vlm"]
    symbols = [s["id"] for s in vision["symbols"]] + [x["ref_id"] for x in vlm_only(context) if "label" in x]
    labels = {s["id"]: s["label"] for s in vision["symbols"]} | {x["ref_id"]: x["label"] for x in vlm_only(context) if "label" in x}
    return {
        "status": "awaiting_approval" if confidence and confidence["passed"] else "needs_review",
        "assembly_path": corrections.get("part") or context["part"]["assembly_path"],
        "marking": {
            "raw_text": " ".join(reading_order(vision, context, texts)),
            "symbols": [texts.get(i, labels[i]) for i in symbols],
            "interpretation": corrections.get("interpretation") or (vlm["interpretation"] if vlm else ", ".join(
                m for m in (meanings.get(d["ref_ids"][0], d["meaning"]) for d in context["dictionary_matches"]) if m)),
        },
        "welding_condition": {k: wc[k] for k in api.WeldingCondition.model_fields} if wc else None,
        "confidence": {k: confidence[k] for k in api.Confidence.model_fields} if confidence else None,
        "evidence": [e["message"] for e in confidence["evidence"]] if confidence else [],
        "needs_review": [n["message"] for n in confidence["needs_review"]] if confidence else [],
    }


def api_errors(analysis: dict, registry: Registry) -> list[str]:
    """to_job_fields 결과가 팀원 Pydantic Job 모델을 통과하는지, 통과(awaiting_approval)면 로봇 JSON 스키마도 통과하는지"""
    fields = to_job_fields(analysis)
    job = {
        "id": analysis["job_id"], "workspace_id": analysis["workspace_id"], "project_id": analysis["project_id"],
        "name": "검증용", "created_at": analysis["created_at"], **fields,
    }
    errors = []
    if fields["status"] not in get_args(api.JobStatus):
        errors.append(f"Job.status '{fields['status']}'가 팀원 JobStatus에 없음")
    try:
        api.Job.model_validate(job)
    except Exception as e:  # pydantic.ValidationError
        errors.append(f"팀원 Job 모델 검증 실패: {e}")
    if fields["status"] == "awaiting_approval":  # 승인하면 바로 로봇 JSON을 만들 수 있어야 함
        robot = {
            "job_id": job["id"], "workspace_id": job["workspace_id"], "project_id": job["project_id"],
            "created_at": job["created_at"], "approved": True, "approved_by": "검증용",
            **{k: fields[k] for k in ("assembly_path", "marking", "welding_condition", "confidence", "evidence", "needs_review")},
        }
        errors += [f"로봇 JSON: {e}" for e in schema_errors(robot, "robot_output.schema.json", registry)]
    return errors


def seed_errors(analysis: dict) -> list[str]:
    """예시가 팀원 시드 DB(사전·조립 트리·용접 기준)와 맞는지 = 예시 자체의 DB 정합성"""
    errors = []
    ws_dir = SEED / "workspaces" / analysis["workspace_id"]
    project_dir = ws_dir / "projects" / analysis["project_id"]
    if not project_dir.is_dir():
        return [f"시드에 워크스페이스/프로젝트 {analysis['workspace_id']}/{analysis['project_id']} 없음"]
    codes = {e["code"] for e in json.loads((ws_dir / "symbol_dictionary.json").read_text(encoding="utf-8"))["entries"]}
    with open(project_dir / "assembly_tree.csv", newline="", encoding="utf-8") as f:
        tree = {row["node_id"]: row for row in csv.DictReader(f)}
    with open(SEED / "welding_standards.csv", newline="", encoding="utf-8") as f:
        standards = list(csv.DictReader(f))

    for s in analysis["vision"]["symbols"]:
        if s["label"] != "unknown" and s["label"] not in codes:
            errors.append(f"vision {s['id']}: label '{s['label']}'가 사전에 없음")
    for m in analysis["context"]["dictionary_matches"]:
        if m["code"] and m["code"] not in codes:
            errors.append(f"dictionary_matches: code '{m['code']}'가 사전에 없음")
    part = analysis["context"]["part"]
    node = tree.get(part["node_id"] or "")
    if part["found_in_tree"] != bool(node and node["path"] == part["assembly_path"]):
        errors.append(f"part: found_in_tree({part['found_in_tree']})가 조립 트리와 다름")
    wc = analysis["context"]["welding_condition"]
    if wc and wc["standard_matched"]:
        keys = ("joint_type", "process", "position", "current_a", "voltage_v", "speed_cm_min")
        match = [
            r for r in standards
            if all(r[k] == wc[k] for k in keys)
            and (wc["thickness_mm"] is None
                 or float(r["thickness_min_mm"]) <= wc["thickness_mm"] <= float(r["thickness_max_mm"]))
        ]
        if not match:
            errors.append("welding_condition: standard_matched인데 용접 기준표에 맞는 행이 없음")
    return errors


def flow_errors(ex: dict) -> list[str]:
    """예시끼리 이어지는지: 1·2·3단계 예시 = analysis 묶음, revision 1 → 작업자 확인 → revision 2"""
    errors = []
    rev1, rev2 = ex["analysis.example.json"], ex["analysis_revision2.example.json"]
    for part, name in (("vision", "vision_result"), ("context", "context_result"), ("confidence", "confidence_report")):
        if rev1[part] != ex[f"{name}.example.json"]:
            errors.append(f"analysis.{part}가 {name}.example.json과 다름")
    for key in ("workspace_id", "project_id", "job_id", "image_id"):
        if rev1[key] != rev2[key]:
            errors.append(f"revision 2의 {key}가 revision 1과 다름")
    if rev2["revision"] != rev1["revision"] + 1:
        errors.append("revision 2 번호가 revision 1 + 1이 아님")
    if rev2["vision"] != rev1["vision"]:
        errors.append("revision 2에서 1단계 결과가 바뀜 (작업자 확인은 1단계를 다시 돌리지 않음)")
    if to_job_fields(rev1)["status"] != "needs_review" or to_job_fields(rev2)["status"] != "awaiting_approval":
        errors.append("예시 흐름은 revision 1 needs_review → revision 2 awaiting_approval 이어야 함")
    return errors


def report(name: str, errors: list[str]) -> bool:
    print(f"{'OK ' if not errors else 'ERR'} {name}")
    for e in errors:
        print(f"    {e}")
    return not errors


def main() -> int:
    registry = load_registry()
    examples = {name: json.loads((EXAMPLES / name).read_text(encoding="utf-8")) for name in EXAMPLE_SCHEMAS}
    results = []
    for name, ref in EXAMPLE_SCHEMAS.items():
        errors = schema_errors(examples[name], ref, registry)
        if not errors and ref == "analysis.schema.json":
            errors = semantic_errors(examples[name]) + seed_errors(examples[name]) + api_errors(examples[name], registry)
        results.append(report(name, errors))
    if all(results):
        results.append(report("흐름: 1→2→3단계 → 작업자 확인 → revision 2", flow_errors(examples)))

    print(f"\n{sum(results)}/{len(results)} 통과")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
