"""실제 모델로 1→2→3단계 전체를 돌려 정답(data/annotations)과 비교 — CI 는 모델 없이 돌아서 실제 OCR·VLM 이 깨져도 못 잡음

사진은 data/annotations/README.md 규칙대로 data/raw/<image> 에 둔다 (운영측 PAC 사진은 저장소에 없음 — 드라이브에서 받기).
.env 의 VLM 설정을 그대로 쓴다 (VLM_PROVIDER=off 면 OCR + DB 대조만). VLM 을 켜면 사진마다 VLM_RUNS 번 API 를 부른다.

사용 (저장소 루트에서):
  backend/.venv/bin/python backend/tools/eval_pipeline.py                 # pac_* 정답 전부
  backend/.venv/bin/python backend/tools/eval_pipeline.py pac_handwriting  # 이름이 이걸로 시작하는 정답만
  옵션: --raw <사진 폴더> (기본 data/raw) · --out <결과 json> (기본 data/eval/pipeline.json)

재는 것: 글자 정답 중 1단계(OCR) · 2단계가 해석에 쓴 읽기(OCR + VLM)와 같은 것, 각장(F·V·S) 정답 중 맞힌 것,
셀 형태 기호 수, 단계 사이 스키마·규칙 오류, 신뢰도 · 상태 · 시간
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

from vision.image import load_image  # noqa: E402
from vw_shared import schema_errors, semantic_errors  # noqa: E402

from app.pipeline import analyze_image, job_with_analysis  # noqa: E402
from app.schemas import JobCreate  # noqa: E402
from app.store import reset_store  # noqa: E402

LEG = re.compile(r"^[FVS][0-9]+(?:\.[0-9]+)?$")


def norm(text: str) -> str:
    return re.sub(r"\s+", "", text).upper()


def leg_value(text: str) -> tuple[str, float] | None:
    text = norm(text)
    return (text[0], float(text[1:])) if LEG.match(text) else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("prefix", nargs="?", default="pac_")
    parser.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "eval" / "pipeline.json")
    args = parser.parse_args()

    truths = sorted((ROOT / "data" / "annotations").glob(f"{args.prefix}*.json"))
    if not truths:
        print(f"정답이 없음: data/annotations/{args.prefix}*.json")
        return 1
    store = reset_store()  # 메모리만 (DATABASE_URL 파일을 건드리지 않음)
    rows, totals = [], {"texts": 0, "ocr": 0, "used": 0, "legs": 0, "legs_found": 0, "errors": 0}
    for path in truths:
        truth = json.loads(path.read_text(encoding="utf-8"))
        photo = args.raw / truth["image"]
        if not photo.is_file():
            print(f"{path.stem}: 사진 없음 ({photo.relative_to(ROOT) if photo.is_relative_to(ROOT) else photo}) — 건너뜀")
            continue
        data = photo.read_bytes()
        image = load_image(data)
        job = store.create_job("demo", JobCreate(name=path.stem, project_id="block_a1"))
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
        errors = schema_errors(analysis, "analysis.schema.json") + semantic_errors(analysis)
        row = {
            "photo": path.stem,
            "seconds": round(seconds, 1),
            "errors": errors,
            "texts": len(truth_texts),
            "ocr_exact": sum(t in ocr for t in truth_texts),
            "used_exact": sum(t in used for t in truth_texts),
            "legs": len(truth_legs),
            "legs_found": sum(leg in found_legs for leg in truth_legs),
            "truth_legs": [f"{c}{v:g}" for c, v in truth_legs],
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
        for key in ("texts", "legs", "legs_found"):
            totals[key] += row[key]
        totals["ocr"] += row["ocr_exact"]
        totals["used"] += row["used_exact"]
        totals["errors"] += len(errors)
        legs = f"각장 {row['legs_found']}/{row['legs']}" if row["legs"] else "각장 -"
        print(f"{path.stem:28} {seconds:5.1f}초  글자 OCR {row['ocr_exact']}/{row['texts']} · 해석 {row['used_exact']}/{row['texts']}  "
              f"{legs}  신뢰도 {confidence['overall']:g}  {filled.status}  {'오류 ' + str(len(errors)) if errors else ''}", flush=True)

    if not rows:
        print("돌린 사진이 없음 — --raw 폴더를 확인")
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n합계: 글자 OCR {totals['ocr']}/{totals['texts']} · 해석 {totals['used']}/{totals['texts']}, "
          f"각장 {totals['legs_found']}/{totals['legs']}, 단계 사이 오류 {totals["errors"]}건 → {args.out}")
    return 1 if totals["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
