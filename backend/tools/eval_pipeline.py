"""실제 모델로 1→2→3단계 전체를 돌려 정답(data/annotations)과 비교 — CI 는 모델 없이 돌아서 실제 OCR·VLM 이 깨져도 못 잡음

사진은 data/annotations/README.md 규칙대로 data/raw/<image> 에 둔다 (운영측 PAC 사진은 저장소에 없음 — 드라이브에서 받기).
.env 의 VLM 설정을 그대로 쓴다 (VLM_PROVIDER=off 면 OCR + DB 대조만). VLM 을 켜면 사진마다 VLM_RUNS 번 API 를 부른다.

사용 (저장소 루트에서):
  backend/.venv/bin/python backend/tools/eval_pipeline.py                 # pac_* 정답 전부
  backend/.venv/bin/python backend/tools/eval_pipeline.py pac_handwriting  # 이름이 이걸로 시작하는 정답만
  옵션: --raw <사진 폴더> (기본 data/raw) · --out <결과 json> (기본 data/eval/pipeline.json)
        --simulate dark,glare,stain,skewed (또는 all) : 사진마다 촬영 조건을 인위적으로 입힌 사진도 돌림 (backend/tools/conditions.py)
        --texts-only : 글자 정답이 없는 사진은 건너뜀

재는 것: 글자 정답 중 1단계(OCR) · 2단계가 해석에 쓴 읽기(OCR + VLM)와 같은 것, 각장(F·V·S) 정답 중 맞힌 것
(1단계 단독 = 1단계가 읽은 글자 토큰이 화살표·기호만 떼면 각장 표기 그대로인 것, 전체 = 2단계가 확정한 각장), 셀 형태 기호 수,
단계 사이 스키마·규칙 오류, 신뢰도 · 상태 · 시간.
묶음별 합계(<out>_groups.json): 원본 전체, 정답 파일의 conditions 별(실제로 그 조건에서 찍은 사진), --simulate 조건별(합성)
— 발표의 "Vision AI 단독 vs Vision AI + DB + VLM" 비교 숫자
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=False)

import cv2  # noqa: E402
from vision.image import load_image  # noqa: E402
from vw_shared import schema_errors, semantic_errors  # noqa: E402

from app.pipeline import analyze_image, job_with_analysis  # noqa: E402
from app.schemas import JobCreate  # noqa: E402
from app.store import reset_store  # noqa: E402

from conditions import LABELS, simulate  # noqa: E402 — 같은 폴더 (backend/tools)

LEG = re.compile(r"^[FVS][0-9]+(?:\.[0-9]+)?$")
NOT_MARKING = re.compile(r"[^A-Z0-9.]")  # 화살표·기호 (→F7.5 의 →) — 글자는 남김 (PF5.0 은 각장이 아님)


def norm(text: str) -> str:
    return re.sub(r"\s+", "", text).upper()


def leg_value(text: str) -> tuple[str, float] | None:
    text = norm(text)
    return (text[0], float(text[1:])) if LEG.match(text) else None


def ocr_legs(texts: list[dict]) -> set[tuple[str, float]]:
    """1단계 단독 의미 해석: 1단계가 읽은 글자 토큰이 화살표·기호만 떼면 각장 표기 그대로인 것 (2단계의 값 보정·DB·VLM 없이).
    PF5.0(화살표를 P로 읽음)처럼 다른 글자가 붙으면 각장으로 치지 않음 — 2단계도 그대로는 각장으로 못 씀"""
    return {leg for t in texts for token in t["text"].upper().split() if (leg := leg_value(NOT_MARKING.sub("", token)))}


def percent(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def group_totals(rows: list[dict]) -> dict:
    """묶음 합계 — 글자(문자 인식)와 각장(의미 해석) 각각 1단계 단독 vs 전체, 복합 = (맞힌 글자 + 맞힌 각장) ÷ (글자 + 각장 정답)"""
    t = {key: sum(r[key] for r in rows) for key in ("texts", "ocr_exact", "used_exact", "legs", "legs_ocr", "legs_found")}
    return {"photos": len(rows), **t,
            "text_alone_pct": percent(t["ocr_exact"], t["texts"]), "text_full_pct": percent(t["used_exact"], t["texts"]),
            "leg_alone_pct": percent(t["legs_ocr"], t["legs"]), "leg_full_pct": percent(t["legs_found"], t["legs"]),
            "combined_alone_pct": percent(t["ocr_exact"] + t["legs_ocr"], t["texts"] + t["legs"]),
            "combined_full_pct": percent(t["used_exact"] + t["legs_found"], t["texts"] + t["legs"])}


def groups_of(rows: list[dict]) -> dict[str, dict]:
    originals = [r for r in rows if not r["simulated"]]
    groups = {"원본 전체": group_totals(originals)}
    for tag in sorted({c for r in originals for c in r["conditions"]}):
        groups[f"실제 {tag}"] = group_totals([r for r in originals if tag in r["conditions"]])
    for tag in dict.fromkeys(r["simulated"] for r in rows if r["simulated"]):
        groups[f"합성 {LABELS.get(tag, tag)}"] = group_totals([r for r in rows if r["simulated"] == tag])
    return groups


def run_photo(store, path: Path, photo: Path, truth: dict, condition: str | None, data: bytes, rows: list[dict]) -> int:
    """사진 한 장(원본 또는 조건을 입힌 것)을 1→2→3단계로 해석해 정답과 비교한 행을 rows 에 붙임 → 단계 사이 오류 수"""
    image = load_image(data)
    name = path.stem + (f"+{condition}" if condition else "")
    job = store.create_job("demo", JobCreate(name=name, project_id="block_a1"))
    stored = store.add_image(job, photo.name, "image/png", data, image.shape[1], image.shape[0])
    start = time.perf_counter()
    analysis = analyze_image(store, job, image, stored.image_id)
    seconds = time.perf_counter() - start
    filled = job_with_analysis(job, analysis)
    vision, context, confidence = analysis["vision"], analysis["context"], analysis["confidence"]

    truth_texts = [norm(t["text"]) for t in truth["texts"] if "?" not in t["text"]]
    ocr = {norm(t["text"]) for t in vision["texts"]}
    used = {norm(m["raw"]) for m in context["dictionary_matches"]}
    if context["vlm"]:
        used |= {norm(x["text"]) for x in context["vlm"]["reading"]["texts"]}
    truth_legs = [leg for t in truth["texts"] if (leg := leg_value(t["text"]))]
    found_legs = {(leg["code"], leg["size_mm"]) for leg in context["leg_lengths"]}
    alone_legs = ocr_legs(vision["texts"])
    errors = schema_errors(analysis, "analysis.schema.json") + semantic_errors(analysis)
    row = {
        "photo": path.stem,
        "simulated": condition,
        "conditions": truth.get("conditions", []),
        "seconds": round(seconds, 1),
        "errors": errors,
        "texts": len(truth_texts),
        "ocr_exact": sum(t in ocr for t in truth_texts),
        "used_exact": sum(t in used for t in truth_texts),
        "legs": len(truth_legs),
        "legs_ocr": sum(leg in alone_legs for leg in truth_legs),
        "legs_found": sum(leg in found_legs for leg in truth_legs),
        "truth_legs": [f"{c}{v:g}" for c, v in truth_legs],
        "ocr_texts": [t["text"] for t in vision["texts"]],
        "leg_lengths": [leg["raw_text"] for leg in context["leg_lengths"]],
        "cell": context["cell"],
        "truth_cell_symbols": sum(s["label"] in ("unknown", "slit", "slot", "collar_front", "collar_back", "scallop")
                                  for s in truth["symbols"]),
        "welding_condition": context["welding_condition"],
        "vlm_error": context.get("vlm_error"),
        "confidence": {k: confidence[k] for k in ("visual", "db_consistency", "vlm_reasoning", "overall", "passed")},
        "needs_review": [n["message"] for n in confidence["needs_review"]],
        "conflicts": [(c["type"], c["severity"], c["message"]) for c in context["conflicts"]],
        "status": filled.status,
        "raw_text": filled.marking.raw_text if filled.marking else None,
        "interpretation": filled.marking.interpretation if filled.marking else None,
    }
    rows.append(row)
    legs = f"각장 단독 {row['legs_ocr']} · 전체 {row['legs_found']}/{row['legs']}" if row["legs"] else "각장 -"
    print(f"{name:36} {seconds:5.1f}초  글자 OCR {row['ocr_exact']}/{row['texts']} · 해석 {row['used_exact']}/{row['texts']}  "
          f"{legs}  신뢰도 {confidence['overall']:g}  {filled.status}  {'오류 ' + str(len(errors)) if errors else ''}", flush=True)
    return len(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("prefix", nargs="?", default="pac_")
    parser.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "eval" / "pipeline.json")
    parser.add_argument("--simulate", default="", help="dark,glare,stain,skewed 중 쉼표로 (all = 넷 다)")
    parser.add_argument("--texts-only", action="store_true", help="글자 정답이 없는 사진(셀 기호만 있는 것)은 건너뜀 — VLM 호출 아낌")
    args = parser.parse_args()
    simulated = list(LABELS) if args.simulate == "all" else [c for c in args.simulate.split(",") if c]
    if unknown := [c for c in simulated if c not in LABELS]:
        parser.error(f"--simulate 에 없는 조건: {unknown} (가능: {', '.join(LABELS)})")

    truths = sorted((ROOT / "data" / "annotations").glob(f"{args.prefix}*.json"))
    if not truths:
        print(f"정답이 없음: data/annotations/{args.prefix}*.json")
        return 1
    store = reset_store()  # 메모리만 (DATABASE_URL 파일을 건드리지 않음)
    rows, totals = [], {"errors": 0}
    for path in truths:
        truth = json.loads(path.read_text(encoding="utf-8"))
        if args.texts_only and not any("?" not in t["text"] for t in truth["texts"]):
            print(f"{path.stem}: 글자 정답 없음 — 건너뜀")
            continue
        photo = args.raw / truth["image"]
        if not photo.is_file():
            print(f"{path.stem}: 사진 없음 ({photo.relative_to(ROOT) if photo.is_relative_to(ROOT) else photo}) — 건너뜀")
            continue
        original = photo.read_bytes()
        variants = [(None, original)]
        for condition in simulated:  # 조건을 입힌 사진은 PNG 로 다시 묶어 원본과 같은 길로 넣음
            boxes = [t["bbox"] for t in truth["texts"] if t.get("bbox")]
            changed = simulate(load_image(original), condition, path.stem, boxes)
            variants.append((condition, cv2.imencode(".png", changed)[1].tobytes()))
        for condition, data in variants:
            totals["errors"] += run_photo(store, path, photo, truth, condition, data, rows)
    if not rows:
        print("돌린 사진이 없음 — --raw 폴더를 확인")
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    groups = groups_of(rows)
    groups_path = args.out.with_name(args.out.stem + "_groups.json")
    groups_path.write_text(json.dumps(groups, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{'묶음':16} {'사진':>4}  {'글자 단독':>9} {'글자 전체':>9}  {'각장 단독':>9} {'각장 전체':>9}  {'복합 단독':>9} {'복합 전체':>9}")
    for name, g in groups.items():
        cells = [f"{g[k]:>8}%" if g[k] is not None else f"{'-':>9}" for k in
                 ("text_alone_pct", "text_full_pct", "leg_alone_pct", "leg_full_pct", "combined_alone_pct", "combined_full_pct")]
        print(f"{name:16} {g['photos']:>4}  {cells[0]} {cells[1]}  {cells[2]} {cells[3]}  {cells[4]} {cells[5]}")
    whole = groups["원본 전체"]
    print(f"\n원본 합계: 글자 OCR {whole['ocr_exact']}/{whole['texts']} · 해석 {whole['used_exact']}/{whole['texts']}, "
          f"각장 단독 {whole['legs_ocr']} · 전체 {whole['legs_found']}/{whole['legs']}, 단계 사이 오류 {totals['errors']}건 "
          f"→ {args.out}, {groups_path.name}")
    return 1 if totals["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
