"""검출기 학습 데이터 묶기: 합성 장면 + steel-ocr 실제 표기 사진 + 운영측 사진 → PaddleOCR 검출 학습 형식 한 폴더

- 합성 장면(synth_handwriting.py --mode scenes): 손글씨 각장 표기 위치를 배움
- steel-ocr 실제 사진: 철판 위 페인트 표기 — 손글씨만 배우다 기존 표기를 못 찾게 되지 않도록 섞음.
  steel-ocr은 표기 일부에만 정답 상자가 있어서(AYa1 같은 표기는 빠짐), 지금 검출기가 찾은 영역 중 정답과 겹치지 않는 곳을
  "###"(무시)로 표시 — 정답 없는 실제 표기를 배경으로 배우지 않게 함 (--ignore-with-detector)
- 운영측 사진(data/annotations/pac_*.json): 평가 전용. 1단계 파이프라인처럼 긴 변 1280px로 키움 (노이즈 제거 없음)

사용:
  python vision/tools/build_det_data.py --out data/synth/hw_det_v2 \\
      --synth-train data/synth/det_train --synth-val data/synth/det_val \\
      --steel-train data/raw/external/steel-ocr/train_data/det/train.txt \\
      --steel-val data/raw/external/steel-ocr/train_data/det/val.txt --pac --ignore-with-detector
출력: <out>/<세트>/images/*.jpg 와 목록 파일 <out>/train.txt · val_synth.txt · val_steel.txt · val_pac.txt
      (목록의 경로는 <out> 기준 — PaddleOCR 설정의 data_dir = <out>)
"""
import argparse
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def scaled(img: np.ndarray, max_side: int, upscale: bool) -> tuple[np.ndarray, float]:
    s = max_side / max(img.shape[:2])
    if s > 1 and not upscale:
        return img, 1.0
    interp = cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA
    return cv2.resize(img, None, fx=s, fy=s, interpolation=interp), s


def center_inside(poly, boxes, margin=0.1) -> bool:
    cx, cy = np.asarray(poly, float).mean(0)
    for b in boxes:
        xs, ys = [p[0] for p in b], [p[1] for p in b]
        mx, my = (max(xs) - min(xs)) * margin, (max(ys) - min(ys)) * margin
        if min(xs) - mx <= cx <= max(xs) + mx and min(ys) - my <= cy <= max(ys) + my:
            return True
    return False


class Detector:
    """지금 1단계 검출기 (vision.ocr.DEFAULT_CONFIG) — 정답 없는 표기를 찾아 무시 영역으로"""

    def __init__(self):
        from paddleocr import TextDetection

        from vision.ocr import DEFAULT_CONFIG as c

        self.model = TextDetection(model_name=c.det_model, limit_side_len=c.det_limit_side_len,
                                   limit_type=c.det_limit_type, enable_mkldnn=False)

    def polys(self, img: np.ndarray) -> list:
        return [np.asarray(p).round().astype(int).tolist() for p in list(self.model.predict(img))[0]["dt_polys"]]


def copy_synth(src: Path, out: Path, tag: str) -> list[str]:
    """합성 장면 폴더(det_labels.txt) → <out>/<tag>, 경로에 tag 를 붙인 목록 줄"""
    shutil.copytree(src / "images", out / tag / "images", dirs_exist_ok=True)
    lines = []
    for line in (src / "det_labels.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            rel, boxes = line.split("\t", 1)
            lines.append(f"{tag}/{rel}\t{boxes}")
    return lines


def add_steel(label_file: Path, out: Path, tag: str, max_side: int, detector: Detector | None) -> tuple[list[str], int]:
    """steel-ocr 검출 목록 → 긴 변 max_side 로 줄여 저장, 좌표도 줄임. (목록 줄, 무시 영역 수)"""
    (out / tag / "images").mkdir(parents=True, exist_ok=True)
    lines, ignored = [], 0
    for line in label_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rel, labels = line.split("\t", 1)
        img = cv2.imread(str(label_file.parent / rel))
        if img is None:
            continue
        img, s = scaled(img, max_side, upscale=False)
        boxes = [{"transcription": lab["transcription"], "points": (np.asarray(lab["points"], float) * s).round().astype(int).tolist()}
                 for lab in json.loads(labels)]
        if detector:
            gts = [b["points"] for b in boxes]
            extra = [p for p in detector.polys(img) if not center_inside(p, gts)]
            boxes += [{"transcription": "###", "points": p} for p in extra]
            ignored += len(extra)
        name = f"{tag}/images/{Path(rel).stem}.jpg"
        cv2.imwrite(str(out / name), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        lines.append(f"{name}\t{json.dumps(boxes, ensure_ascii=False)}")
    return lines, ignored


def add_pac(out: Path, tag: str, max_side: int) -> list[str]:
    """운영측 사진 정답(data/annotations/pac_*.json, 글자 상자가 있는 것만) → 1단계처럼 키워 저장"""
    (out / tag / "images").mkdir(parents=True, exist_ok=True)
    lines = []
    for ann_path in sorted((ROOT / "data/annotations").glob("pac_*.json")):
        ann = json.loads(ann_path.read_text(encoding="utf-8"))
        texts = [t for t in ann["texts"] if t.get("bbox")]
        img = cv2.imread(str(ROOT / "data/raw" / ann["image"]))
        if img is None or not texts:
            continue
        img, s = scaled(img, max_side, upscale=True)
        boxes = [{"transcription": t["text"], "points": [[round(x * s), round(y * s)] for x, y in
                                                          [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]]}
                 for t in texts for x1, y1, x2, y2 in [t["bbox"]]]
        name = f"{tag}/images/{ann_path.stem}.jpg"
        cv2.imwrite(str(out / name), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        lines.append(f"{name}\t{json.dumps(boxes, ensure_ascii=False)}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--synth-train", type=Path)
    parser.add_argument("--synth-val", type=Path)
    parser.add_argument("--steel-train", type=Path)
    parser.add_argument("--steel-val", type=Path)
    parser.add_argument("--pac", action="store_true")
    parser.add_argument("--max-side", type=int, default=1280, help="1단계 검출 기준 (vision.ocr.OcrConfig.det_limit_side_len)")
    parser.add_argument("--ignore-with-detector", action="store_true", help="steel-ocr의 정답 없는 표기를 무시 영역으로")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    detector = Detector() if args.ignore_with_detector and (args.steel_train or args.steel_val) else None
    lists: dict[str, list[str]] = {"train": [], "val_synth": [], "val_steel": [], "val_pac": []}
    if args.synth_train:
        lists["train"] += copy_synth(args.synth_train, args.out, "synth_train")
    if args.synth_val:
        lists["val_synth"] += copy_synth(args.synth_val, args.out, "synth_val")
    for key, path, tag in (("train", args.steel_train, "steel_train"), ("val_steel", args.steel_val, "steel_val")):
        if path:
            lines, ignored = add_steel(path, args.out, tag, args.max_side, detector)
            lists[key] += lines
            print(f"{tag}: 사진 {len(lines)}장, 정답 없는 표기 무시 영역 {ignored}개")
    if args.pac:
        lists["val_pac"] += add_pac(args.out, "pac", args.max_side)
    for name, lines in lists.items():
        if lines:
            (args.out / f"{name}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"{name}.txt: {len(lines)}장")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
