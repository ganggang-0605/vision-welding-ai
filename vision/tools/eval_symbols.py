"""기호 검출 평가: data/annotations 정답 ↔ GroundingDINO 제로샷 (YOLOX를 붙이면 같은 지표로 비교)

GroundingDINO는 실험 기록용 — 결과와 연결하지 않은 이유: vision/reports/phase3_groundingdino.md

사용:
  backend/.venv/bin/python vision/tools/eval_symbols.py --limit 1                     # 빠른 확인
  backend/.venv/bin/python vision/tools/eval_symbols.py --prompts descriptive --model IDEA-Research/grounding-dino-base \\
      --out vision/reports/runs/symbols_base.json --draw
  원격(Claude Managed Agents)으로: vision/tools/remote_symbols.py
지표: 기호(label)마다 AP · 재현율 · 정밀도, IoU 0.5와 0.3 두 기준 (가는 화살표는 상자가 조금만 어긋나도 IoU가 낮음).
      "any"는 label을 무시하고 위치만 맞춘 결과 — 문구를 잘못 붙였어도 기호 자리를 찾았는지 봄
정답 형식: data/annotations/README.md (PAC 사진의 "unknown"은 셀 끝 절단부)
"""
import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import cv2

from vision.symbols import DEFAULT_GROUNDING_DINO, config_dict, detect_grounding_dino, grounding_dino_available

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
ANNOTATIONS = ROOT / "data" / "annotations"

# 문구끼리 단어가 겹치지 않게 (vision.symbols.phrase_to_code)
PROMPT_SETS = {
    "simple": (("arrow", "→"), ("cross", "+"), ("hole", "unknown")),
    "descriptive": (("handwritten arrow", "→"), ("cross mark", "+"), ("semicircular cutout", "unknown")),
}
COLLECT_THRESHOLD = 0.1  # AP를 구하려고 낮은 점수까지 모아 두고, 점수 기준값별 결과는 아래 값들로 따로 셈
SCORE_THRESHOLDS = (0.2, 0.3, 0.4)
IOU_THRESHOLDS = (0.5, 0.3)
DRAW_NAMES = {"→": "arrow", "+": "mark", "unknown": "cutout"}  # OpenCV 글꼴에 없는 글자 대신


def load_samples(split: str) -> list[tuple[str, Path, list[dict]]]:
    """(정답 파일 이름, 사진 경로, 위치가 있는 기호 정답). 제로샷 평가라 기본은 split 구분 없이 전부"""
    samples = []
    for path in sorted(ANNOTATIONS.glob("*.json")):
        ann = json.loads(path.read_text(encoding="utf-8"))
        if split != "all" and ann.get("split") != split:
            continue
        gts = [s for s in ann["symbols"] if s.get("bbox")]
        samples.append((path.stem, RAW / ann["image"], gts))
    return samples


def iou(a: list, b: list) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def match(gts: dict[int, list], preds: list[tuple[float, int, list]], iou_min: float) -> list[tuple[float, bool]]:
    """점수 높은 예측부터 같은 사진의 아직 안 짝지은 정답 중 IoU가 가장 큰 것과 짝지음 → (점수, 맞음 여부) 점수 내림차순"""
    used = {i: [False] * len(boxes) for i, boxes in gts.items()}
    hits = []
    for score, i, box in sorted(preds, key=lambda p: -p[0]):
        best, best_j = 0.0, None
        for j, g in enumerate(gts.get(i, [])):
            if not used[i][j] and (o := iou(box, g)) > best:
                best, best_j = o, j
        ok = best >= iou_min
        if ok:
            used[i][best_j] = True
        hits.append((score, ok))
    return hits


def average_precision(hits: list[tuple[float, bool]], n_gt: int) -> float | None:
    """VOC 방식 (재현율 구간마다 그 뒤 최대 정밀도로 넓이)"""
    if not n_gt:
        return None
    tp, points = 0, []
    for k, (_, ok) in enumerate(hits, 1):
        tp += ok
        points.append((tp / n_gt, tp / k))
    ap, prev_recall = 0.0, 0.0
    for k, (recall, _) in enumerate(points):
        ap += (recall - prev_recall) * max(p for _, p in points[k:])
        prev_recall = recall
    return round(ap, 4)


def summarize(results: list[dict]) -> dict:
    labels = sorted({g["label"] for r in results for g in r["gts"]} | {p["label"] for r in results for p in r["preds"]})
    summary = {}
    for label in [*labels, "any"]:
        gts = {i: [g["bbox"] for g in r["gts"] if label in ("any", g["label"])] for i, r in enumerate(results)}
        preds = [(p["prob"], i, p["bbox"]) for i, r in enumerate(results) for p in r["preds"] if label in ("any", p["label"])]
        n_gt = sum(len(v) for v in gts.values())
        row = {"gt": n_gt}
        for iou_min in IOU_THRESHOLDS:
            hits = match(gts, preds, iou_min)
            row[f"ap@{iou_min}"] = average_precision(hits, n_gt)
            for t in SCORE_THRESHOLDS:
                kept = [ok for score, ok in hits if score >= t]
                tp = sum(kept)
                row[f"iou{iou_min}_score{t}"] = {
                    "tp": tp, "fp": len(kept) - tp, "fn": n_gt - tp,
                    "recall": round(tp / n_gt, 3) if n_gt else None,
                    "precision": round(tp / len(kept), 3) if kept else None,
                }
        summary[label] = row
    return summary


def draw(image, gts: list[dict], preds: list[dict], min_score: float, path: Path) -> None:
    """정답 초록, 예측 빨강(점수 함께). 큰 사진은 긴 변 1600px로 줄이고, 작은 사진은 3배로 키워 글자가 보이게"""
    long_side = max(image.shape[:2])
    scale = 1600 / long_side if long_side > 1600 else 3 if long_side < 600 else 1
    canvas = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    corners = lambda b: ((int(b[0] * scale), int(b[1] * scale)), (int(b[2] * scale), int(b[3] * scale)))
    for g in gts:
        cv2.rectangle(canvas, *corners(g["bbox"]), (0, 200, 0), 2)
    for p in preds:
        if p["prob"] < min_score:
            continue
        top_left, bottom_right = corners(p["bbox"])
        cv2.rectangle(canvas, top_left, bottom_right, (0, 0, 255), 2)
        cv2.putText(canvas, f"{DRAW_NAMES.get(p['label'], p['label'])} {p['prob']:.2f}",
                    (top_left[0] + 2, max(12, top_left[1] - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1, cv2.LINE_AA)
    cv2.imwrite(str(path), canvas, [cv2.IMWRITE_JPEG_QUALITY, 85])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=DEFAULT_GROUNDING_DINO.model, help="Hugging Face 모델 (grounding-dino-tiny · -base)")
    parser.add_argument("--prompts", choices=sorted(PROMPT_SETS), default="simple")
    parser.add_argument("--text-threshold", type=float, default=0.2)
    parser.add_argument("--split", choices=["all", "train", "eval"], default="all")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--draw", action="store_true", help="정답·예측 상자를 그린 사진을 --out 옆에 저장 (<out 이름>_<정답 이름>.jpg)")
    parser.add_argument("--draw-min", type=float, default=0.25, help="그림에 표시할 최소 점수")
    parser.add_argument("--out", type=Path, default=ROOT / "vision/reports/runs/eval_symbols.json")
    args = parser.parse_args()

    if not grounding_dino_available():
        print('torch · transformers가 없습니다 (pip install -e "vision[models]")', file=sys.stderr)
        return 1
    config = replace(DEFAULT_GROUNDING_DINO, model=args.model, prompts=PROMPT_SETS[args.prompts],
                     box_threshold=COLLECT_THRESHOLD, text_threshold=args.text_threshold)
    samples = load_samples(args.split)[:args.limit]
    if not samples:
        print("평가할 정답이 없습니다 (data/annotations)", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    results, times = [], []
    for name, path, gts in samples:
        image = cv2.imread(str(path))  # EXIF 회전 적용 — 정답 좌표도 같은 방향 기준
        start = time.perf_counter()
        preds = detect_grounding_dino(image, config)
        times.append(time.perf_counter() - start)
        results.append({"name": name, "image": str(path.relative_to(ROOT)), "size": list(image.shape[1::-1]),
                        "gts": gts, "preds": preds})
        print(f"{name}: 정답 {len(gts)} · 예측 {len(preds)} (점수 {args.draw_min} 이상 "
              f"{sum(p['prob'] >= args.draw_min for p in preds)}) · {times[-1]:.1f}초", file=sys.stderr)
        if args.draw:
            draw(image, gts, preds, args.draw_min, args.out.parent / f"{args.out.stem}_{name}.jpg")

    report = {
        "config": {**config_dict(config), "prompt_set": args.prompts, "split": args.split, "images": len(samples)},
        "summary": {"sec_per_image_mean": round(sum(times) / len(times), 2), "by_label": summarize(results)},
        "images": results,
    }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
