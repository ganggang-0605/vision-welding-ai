"""shared 점검: 예시가 스키마에 맞는지, 단계 사이 규칙, 시드 DB와 맞는지, 예시끼리 이어지는지

사용: python -m vw_shared.validate   (pip install -e shared 후)
팀원 Pydantic 모델(backend/app/schemas.py)과 맞는지는 backend/tests/test_pipeline.py가 점검
"""
import csv
import json
import sys

from vw_shared.job_fields import to_job_fields
from vw_shared.rules import semantic_errors
from vw_shared.schemas import SHARED, load_example, schema_errors

SEED = SHARED.parent / "data" / "seed"

EXAMPLE_SCHEMAS = {
    "vision_result.example.json": "vision_result.schema.json",
    "context_input.example.json": "context_input.schema.json",
    "context_result.example.json": "context_result.schema.json",
    "confidence_report.example.json": "confidence_report.schema.json",
    "analysis.example.json": "analysis.schema.json",
    "analysis_revision2.example.json": "analysis.schema.json",
}


def robot_errors(analysis: dict) -> list[str]:
    """통과(awaiting_approval)한 결과는 승인하면 바로 로봇 JSON을 만들 수 있어야 함"""
    fields = to_job_fields(analysis)
    if fields["status"] != "awaiting_approval":
        return []
    robot = {
        "job_id": analysis["job_id"], "workspace_id": analysis["workspace_id"], "project_id": analysis["project_id"],
        "created_at": analysis["created_at"], "approved": True, "approved_by": "검증용",
        **{k: fields[k] for k in ("assembly_path", "marking", "welding_condition", "confidence", "evidence", "needs_review")},
        "cell": fields["cell"], "leg_lengths": fields["leg_lengths"],
    }
    return [f"로봇 JSON: {e}" for e in schema_errors(robot, "robot_output.schema.json")]


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
            and (wc["thickness_mm"] is None or not r["thickness_min_mm"]
                 or float(r["thickness_min_mm"]) <= wc["thickness_mm"] <= float(r["thickness_max_mm"]))
            and (wc.get("leg_length_mm") is None or not r["leg_min_mm"]
                 or float(r["leg_min_mm"]) <= wc["leg_length_mm"] <= float(r["leg_max_mm"]))
        ]
        if not match:
            errors.append("welding_condition: standard_matched인데 용접 기준표에 맞는 행이 없음")
    return errors


def context_input_errors(ci: dict) -> list[str]:
    """2단계 입력 예시가 시드 DB를 그대로 옮긴 것인지"""
    ws_dir = SEED / "workspaces" / ci["workspace_id"]
    project_dir = ws_dir / "projects" / ci["project_id"]
    entries = json.loads((ws_dir / "symbol_dictionary.json").read_text(encoding="utf-8"))["entries"]
    with open(project_dir / "assembly_tree.csv", newline="", encoding="utf-8") as f:
        tree = [row["node_id"] for row in csv.DictReader(f)]
    with open(SEED / "welding_standards.csv", newline="", encoding="utf-8") as f:
        standards = sum(1 for _ in csv.DictReader(f))
    errors = []
    if [e["code"] for e in ci["symbols"]] != [e["code"] for e in entries]:
        errors.append("symbols가 시드 사전과 다름")
    if [n["node_id"] for n in ci["assembly_tree"]] != tree:
        errors.append("assembly_tree가 시드 조립 트리와 다름")
    if len(ci["welding_standards"]) != standards:
        errors.append("welding_standards가 시드 용접 기준표와 다름")
    return errors


def flow_errors(ex: dict) -> list[str]:
    """예시끼리 이어지는지: 1·2·3단계 예시 = analysis 묶음, revision 1 → 작업자 확인 → revision 2"""
    errors = []
    rev1, rev2 = ex["analysis.example.json"], ex["analysis_revision2.example.json"]
    for part, name in (("vision", "vision_result"), ("context", "context_result"), ("confidence", "confidence_report")):
        if rev1[part] != ex[f"{name}.example.json"]:
            errors.append(f"analysis.{part}가 {name}.example.json과 다름")
    for key in ("workspace_id", "project_id"):
        if rev1[key] != ex["context_input.example.json"][key]:
            errors.append(f"context_input.{key}가 analysis와 다름")
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
    examples = {name: load_example(name) for name in EXAMPLE_SCHEMAS}
    results = []
    for name, ref in EXAMPLE_SCHEMAS.items():
        errors = schema_errors(examples[name], ref)
        if not errors and ref == "analysis.schema.json":
            errors = semantic_errors(examples[name]) + seed_errors(examples[name]) + robot_errors(examples[name])
        if not errors and ref == "context_input.schema.json":
            errors = context_input_errors(examples[name])
        results.append(report(name, errors))
    if all(results):
        results.append(report("흐름: 1→2→3단계 → 작업자 확인 → revision 2", flow_errors(examples)))

    print(f"\n{sum(results)}/{len(results)} 통과")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
