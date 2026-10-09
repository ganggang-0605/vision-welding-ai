"""문자 인식 평가: 정답과 비교해 글자 오류율(CER)·표기 정확도·검출률·처리 시간 계산

사용:
  backend/.venv/bin/python vision/tools/eval_ocr.py --dataset steel-ocr            # 사진 전체 (검출 + 인식)
  backend/.venv/bin/python vision/tools/eval_ocr.py --dataset steel-ocr --mode rec # 잘라낸 글자 이미지 (인식만)
  backend/.venv/bin/python vision/tools/eval_ocr.py --dataset annotations          # data/annotations (조선소 표기)
  backend/.venv/bin/python vision/tools/eval_ocr.py --dataset mpsc --limit 200     # MPSC 테스트 (금속 양각·각인)
  --prep none|up|clahe|up+clahe|up+denoise|default : 전처리 비교 (기본 none = 전처리 없이 OCR만)
  --rec-model, --det-model, --limit-side 로 설정 비교, --out 으로 결과 JSON 저장
  --det-model-dir, --rec-model-dir : 추가 학습한 모델 폴더 (기본은 .env 의 VISION_DET_MODEL_DIR · VISION_REC_MODEL_DIR, "official" = 공식 모델)
  --dataset pac : 운영측 사진 정답 전부 (data/annotations/pac_*.json, split 상관없이 — OCR 학습에는 안 씀)
  --charset steel-ocr : 표기에 쓰일 수 있는 글자만 남기는 후처리 효과 측정 (헷갈리는 글자는 바꾸고 나머지는 버림)
  --zoom : 확대 재판독 켜기 (찾은 영역을 원본 해상도로 잘라 다시 읽음)

데이터셋 설명: vision/DATASETS.md, data/annotations/README.md
"""
import argparse
import json
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path

import cv2

from vision.ocr import DEFAULT_CONFIG, config_dict, models_available, recognize_text
from vision.preprocess import DEFAULT_PREPROCESS, PreprocessConfig, preprocess, to_original_coords
from vision.recognition import assign_ids

ROOT = Path(__file__).resolve().parents[2]

STEEL_OCR = ROOT / "data" / "raw" / "external" / "steel-ocr"
# 학습에 쓸 train 은 빼고 평가용 val + test 만
STEEL_DET = [STEEL_OCR / "train_data/det/val.txt", STEEL_OCR / "test_data/det/test.txt"]
STEEL_REC = [STEEL_OCR / "train_data/rec/rec_gt_val.txt", STEEL_OCR / "test_data/rec/rec_gt_test.txt"]
MPSC = ROOT / "data" / "raw" / "external" / "mpsc" / "MPSC"
ANNOTATIONS = ROOT / "data" / "annotations"
RAW = ROOT / "data" / "raw"


# ── 데이터 불러오기: [(이미지 경로, [{"text", "bbox" | None}])] ──

def load_steel_det() -> list[tuple[Path, list[dict]]]:
    samples = []
    for label_file in STEEL_DET:
        for line in label_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rel, labels = line.split("\t", 1)
            gts = []
            for lab in json.loads(labels):
                xs, ys = [p[0] for p in lab["points"]], [p[1] for p in lab["points"]]
                gts.append({"text": lab["transcription"], "bbox": [min(xs), min(ys), max(xs), max(ys)]})
            samples.append((label_file.parent / rel, gts))
    return samples


def load_steel_rec() -> list[tuple[Path, str]]:
    samples = []
    for label_file in STEEL_REC:
        for line in label_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rel, text = line.split("\t", 1)
                samples.append((label_file.parent / rel, text))
    return samples


def load_mpsc() -> list[tuple[Path, list[dict]]]:
    """테스트 639장. 라벨 한 줄 = x1,y1,…,x4,y4,글자. '###'(판독 불가)은 정답에서 뺌"""
    samples = []
    for label in sorted((MPSC / "annotation/test").glob("gt_img_*.txt"), key=lambda p: int(p.stem.split("_")[-1])):
        gts = []
        for line in label.read_text(encoding="utf-8-sig").splitlines():
            parts = line.strip().split(",", 8)
            if len(parts) < 9 or parts[8] == "###":
                continue
            xs, ys = [float(v) for v in parts[0:8:2]], [float(v) for v in parts[1:8:2]]
            gts.append({"text": parts[8], "bbox": [min(xs), min(ys), max(xs), max(ys)]})
        samples.append((MPSC / "image/test" / f"MPSC_img_{label.stem.split('_')[-1]}.jpg", gts))
    return samples


PREP = {
    "none": None,
    "up": PreprocessConfig(denoise=False, clahe=False),
    "clahe": PreprocessConfig(min_long_side=0, denoise=False, clahe=True),
    "up+clahe": PreprocessConfig(denoise=False, clahe=True),
    "up+denoise": PreprocessConfig(denoise=True, clahe=False),
    "default": DEFAULT_PREPROCESS,
}


def load_annotations(pattern: str = "*.json", eval_only: bool = True) -> list[tuple[Path, list[dict]]]:
    samples = []
    for path in sorted(ANNOTATIONS.glob(pattern)):
        ann = json.loads(path.read_text(encoding="utf-8"))
        if eval_only and ann.get("split") != "eval":
            continue
        samples.append((RAW / ann["image"], [{"text": t["text"], "bbox": t.get("bbox")} for t in ann["texts"]]))
    return samples


# ── 허용 글자 후처리 (평가 옵션) ──

# 허용 글자에 없을 때 바꿔 볼 비슷한 글자
CONFUSABLE = {"I": "1", "l": "1", "i": "1", "|": "1", "!": "1", "O": "0", "o": "0", "Q": "0", "D": "0",
              "Z": "2", "z": "2", "—": "-", "_": "-", "~": "-", "=": "-"}


def load_charset(name: str) -> set[str]:
    path = STEEL_OCR / "train_data/rec/dict.txt" if name == "steel-ocr" else Path(name)
    return {line for line in path.read_text(encoding="utf-8").splitlines() if line}


def constrain(text: str, charset: set[str]) -> str:
    out = []
    for ch in text:
        if ch in charset:
            out.append(ch)
        elif CONFUSABLE.get(ch) in charset:
            out.append(CONFUSABLE[ch])
    return "".join(out)


# ── 지표 ──

def edit_distance(pred: str, gt: str) -> int:
    """레벤슈타인 거리. 정답의 '?'(사람도 못 읽은 글자)는 무엇과도 일치"""
    prev = list(range(len(gt) + 1))
    for i, p in enumerate(pred, start=1):
        cur = [i]
        for j, g in enumerate(gt, start=1):
            cost = 0 if (p == g or g == "?") else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def normalize(text: str) -> str:
    return "".join(text.split())


def contains_center(box: list, point: tuple[float, float], margin: float = 0.1) -> bool:
    x1, y1, x2, y2 = box
    mx, my = (x2 - x1) * margin, (y2 - y1) * margin
    return x1 - mx <= point[0] <= x2 + mx and y1 - my <= point[1] <= y2 + my


def iou(a: list, b: list) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def match(gts: list[dict], preds: list[dict]) -> list[dict]:
    """정답 표기마다 예측을 짝지음.
    위치가 있으면: 중심이 정답 상자 안에 들어오는 예측들을 읽는 순서대로 이어 붙임 (한 표기가 여러 조각으로 잡혀도 인정)
    위치가 없으면: 글자가 가장 비슷한 예측 하나"""
    used: set[str] = set()
    rows = []
    for gt in gts:
        if gt["bbox"]:
            parts = [
                p for p in preds
                if p["id"] not in used
                and contains_center(gt["bbox"], ((p["bbox"][0] + p["bbox"][2]) / 2, (p["bbox"][1] + p["bbox"][3]) / 2))
            ]
            best_iou = max((iou(gt["bbox"], p["bbox"]) for p in parts), default=0.0)
        else:
            cands = [p for p in preds if p["id"] not in used]
            best = min(cands, key=lambda p: edit_distance(normalize(p["text"]), normalize(gt["text"])), default=None)
            parts, best_iou = ([best] if best else []), None
        used.update(p["id"] for p in parts)
        pred_text = normalize("".join(p["text"] for p in parts))
        gt_text = normalize(gt["text"])
        rows.append({
            "gt": gt_text,
            "pred": pred_text,
            "found": bool(parts),
            "iou": best_iou,
            "dist": edit_distance(pred_text, gt_text),
            "probs": [p["prob"] for p in parts],
        })
    return rows


def summarize(rows: list[dict], times: list[float], extra_preds: int) -> dict:
    total_chars = sum(len(r["gt"]) for r in rows)
    ious = [r["iou"] for r in rows if r["iou"] is not None]
    return {
        "markings": len(rows),
        "cer": round(sum(min(r["dist"], len(r["gt"])) for r in rows) / total_chars, 4) if total_chars else None,
        "exact": round(sum(r["pred"] == r["gt"] for r in rows) / len(rows), 4) if rows else None,
        "exact_ignore_case": round(sum(r["pred"].lower() == r["gt"].lower() for r in rows) / len(rows), 4) if rows else None,
        "found": round(sum(r["found"] for r in rows) / len(rows), 4) if rows else None,
        "iou50": round(sum(i >= 0.5 for i in ious) / len(ious), 4) if ious else None,
        "unmatched_preds": extra_preds,
        "sec_per_image_mean": round(statistics.mean(times), 3) if times else None,
        "sec_per_image_median": round(statistics.median(times), 3) if times else None,
    }


# ── 실행 ──

def run_det(samples, config, limit, charset=None, prep=None):
    rows, times, details, extra = [], [], [], 0
    for path, gts in samples[:limit]:
        image = cv2.imread(str(path))
        start = time.perf_counter()
        if prep:
            height, width = image.shape[:2]
            clean, _, to_original = preprocess(image, prep)
            preds = assign_ids(to_original_coords(recognize_text(clean, config), to_original, width, height), "t")
        else:
            preds = assign_ids(recognize_text(image, config), "t")
        times.append(time.perf_counter() - start)
        if charset:
            preds = [{**p, "text": constrain(p["text"], charset)} for p in preds]
        matched = match(gts, preds)
        used = sum(len(r["probs"]) for r in matched)
        extra += max(0, len(preds) - used)
        rows += matched
        details.append({"image": str(path.relative_to(ROOT)), "rows": matched, "preds": [p["text"] for p in preds]})
    return summarize(rows, times, extra), details


def run_rec(samples, config, limit, charset=None):
    from paddleocr import TextRecognition

    model = TextRecognition(model_name=config.rec_model, model_dir=config.rec_model_dir, enable_mkldnn=config.enable_mkldnn)
    rows, times, details = [], [], []
    for path, gt in samples[:limit]:
        image = cv2.imread(str(path))
        start = time.perf_counter()
        res = model.predict(image)[0]
        times.append(time.perf_counter() - start)
        pred = normalize(res["rec_text"])
        if charset:
            pred = constrain(pred, charset)
        row = {"gt": normalize(gt), "pred": pred, "found": bool(pred), "iou": None,
               "dist": edit_distance(pred, normalize(gt)), "probs": [round(float(res["rec_score"]), 4)]}
        rows.append(row)
        details.append({"image": str(path.relative_to(ROOT)), **row})
    return summarize(rows, times, 0), details


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", choices=["steel-ocr", "mpsc", "annotations", "pac"], default="steel-ocr")
    parser.add_argument("--mode", choices=["det", "rec"], default="det", help="det: 사진 전체, rec: 잘라낸 글자 (steel-ocr만)")
    parser.add_argument("--det-model")
    parser.add_argument("--rec-model")
    parser.add_argument("--det-model-dir", help='추가 학습한 검출 모델 폴더 ("official" = 공식 모델)')
    parser.add_argument("--rec-model-dir", help='추가 학습한 인식 모델 폴더 ("official" = 공식 모델)')
    parser.add_argument("--limit-side", type=int, help="검출 전 긴 변 크기")
    parser.add_argument("--box-thresh", type=float, help="검출 상자 점수 기준 (기본: PaddleOCR 파이프라인 0.6)")
    parser.add_argument("--orientation", action="store_true", help="뒤집힌 글자 줄 보정 켜기")
    parser.add_argument("--zoom", action="store_true", help="확대 재판독 켜기")
    parser.add_argument("--charset", help="허용 글자 후처리: steel-ocr 또는 글자 목록 파일(한 줄에 한 글자)")
    parser.add_argument("--prep", choices=list(PREP), default="none", help="전처리 (기본 none: 전처리 없이)")
    parser.add_argument("--limit", type=int, help="앞에서 N장만")
    parser.add_argument("--out", type=Path, help="결과 JSON 저장 경로")
    args = parser.parse_args()

    config = DEFAULT_CONFIG
    for field, value in (("det_model", args.det_model), ("rec_model", args.rec_model), ("det_limit_side_len", args.limit_side)):
        if value:
            config = replace(config, **{field: value})
    for field, value in (("det_model_dir", args.det_model_dir), ("rec_model_dir", args.rec_model_dir)):
        if value:
            config = replace(config, **{field: None if value == "official" else str(Path(value).resolve())})
    if args.box_thresh is not None:
        config = replace(config, det_box_thresh=args.box_thresh)
    if args.orientation:
        config = replace(config, use_textline_orientation=True)
    if args.zoom:
        config = replace(config, zoom_reread=True)

    if not models_available():
        parser.error('PaddleOCR이 없습니다: pip install -e "vision[models]"')
    charset = load_charset(args.charset) if args.charset else None
    if args.mode == "rec":
        if args.dataset != "steel-ocr":
            parser.error("--mode rec 는 steel-ocr 만 지원")
        summary, details = run_rec(load_steel_rec(), config, args.limit, charset)
    else:
        samples = {"steel-ocr": load_steel_det, "mpsc": load_mpsc, "annotations": load_annotations,
                   "pac": lambda: load_annotations("pac_*.json", eval_only=False)}[args.dataset]()
        if not samples:
            print("평가할 정답이 없습니다 (data/annotations 의 split=eval 파일)")
            return 1
        summary, details = run_det(samples, config, args.limit, charset, PREP[args.prep])

    report = {"dataset": args.dataset, "mode": args.mode, "config": config_dict(config), "prep": args.prep,
              "charset": args.charset, "summary": summary}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({**report, "details": details}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
