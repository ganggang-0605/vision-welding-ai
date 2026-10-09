"""인식기 학습 데이터 묶기: 합성 손글씨(각장 + 일반 글자) + steel-ocr·MPSC 실제 인쇄 글자 → PaddleOCR 인식 학습 형식 한 폴더

인식기 v3는 합성 각장 표기만으로 학습해 무엇을 보든 F·V·S 형식으로 읽게 굳었음 (150 → F5.0 확률 1.00,
steel-ocr 잘라낸 글자 CER 0.17 → 0.64). 실제 인쇄 글자(steel-ocr · MPSC 학습용)와 합성 일반 글자를 섞어 막음.

사용:
  python vision/tools/build_rec_data.py --out data/synth/hw_rec_v4 \\
      --synth data/synth/rec_train_v4 --synth-val data/synth/rec_val_v4 \\
      --steel-train data/raw/external/steel-ocr/train_data/rec/rec_gt_train.txt --steel-repeat 4 \\
      --steel-val data/raw/external/steel-ocr/train_data/rec/rec_gt_val.txt \\
      --steel-val data/raw/external/steel-ocr/test_data/rec/rec_gt_test.txt \\
      --mpsc-train data/raw/external/mpsc/MPSC --mpsc-max 8000 --pac --pac-det weights/det_v3/inference
출력 <out>/ (폴더마다 images/ + labels.tsv, 경로는 그 폴더 기준 — 노트북의 data_dir = <out>/<폴더>)
  rec_train/      학습: 합성(각장·일반 글자) + steel-ocr(--steel-repeat 번 반복) + MPSC 학습용 잘라낸 단어
  rec_val/        합성 평가 글씨체 (학습에 안 쓴 글꼴)
  steel_rec_val/  steel-ocr val + test 잘라낸 인쇄 표기 — 인쇄체가 나빠지지 않았는지
  pac_rec/        운영측 손글씨 줄 — 사람이 그린 상자 (평가 전용)
  pac_rec_det/    운영측 손글씨 줄 — 검출기(--pac-det)가 실제로 잡은 상자 (평가 전용, 1단계가 인식기에 넘기는 모양)
  val_select.tsv  학습 중 최고 모델 고르기용 = rec_val + steel_rec_val (경로는 <out> 기준) — 운영측은 안 씀
"""
import argparse
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

from vision.candidates import min_area_quad, rotate_crop  # PaddleOCR 이 인식기에 넘기는 것과 같은 자르기

ROOT = Path(__file__).resolve().parents[2]


def write_part(out: Path, part: str, lines: list[str]) -> None:
    (out / part).mkdir(parents=True, exist_ok=True)
    (out / part / "labels.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{part}: {len(lines)}줄")


def copy_lines(src: Path, out_part: Path, tag: str) -> list[str]:
    """synth_handwriting.py --mode lines 폴더(labels.tsv) → <out_part>/images/<tag>/"""
    shutil.copytree(src / "images", out_part / "images" / tag, dirs_exist_ok=True)
    lines = []
    for line in (src / "labels.tsv").read_text(encoding="utf-8").splitlines():
        if line.strip():
            rel, label = line.split("\t", 1)
            lines.append(f"images/{tag}/{Path(rel).name}\t{label}")
    return lines


def copy_steel(label_file: Path, out_part: Path, tag: str, repeat: int = 1) -> list[str]:
    """steel-ocr 잘라낸 글자 목록 → <out_part>/images/<tag>/ (파일 이름 앞에 목록 이름을 붙여 val·test가 겹치지 않게)"""
    (out_part / "images" / tag).mkdir(parents=True, exist_ok=True)
    lines = []
    for line in label_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rel, label = line.split("\t", 1)
        name = f"{label_file.stem}_{Path(rel).name}"
        shutil.copy(label_file.parent / rel, out_part / "images" / tag / name)
        lines += [f"images/{tag}/{name}\t{label}"] * repeat
    return lines


def add_mpsc(mpsc: Path, out_part: Path, tag: str, max_n: int, rng: np.random.Generator) -> list[str]:
    """MPSC 학습용(annotation/train) 단어를 잘라 저장 — 판독 불가(###)·너무 작은 것은 뺌. 평가용(test)은 안 씀"""
    words = []
    for label in sorted((mpsc / "annotation/train").glob("gt_img_*.txt")):
        for k, line in enumerate(label.read_text(encoding="utf-8-sig").splitlines()):
            parts = line.strip().split(",", 8)
            if len(parts) == 9 and parts[8] not in ("", "###"):
                words.append((label.stem.split("_")[-1], k, [float(v) for v in parts[:8]], parts[8]))
    picked = sorted(rng.choice(len(words), min(max_n, len(words)), replace=False))
    (out_part / "images" / tag).mkdir(parents=True, exist_ok=True)
    lines, cache = [], {}
    for i in picked:
        img_id, k, coords, text = words[i]
        if img_id not in cache:
            cache.clear()  # 같은 사진의 단어는 붙어 있음 — 한 장만 들고 있음
            cache[img_id] = cv2.imread(str(mpsc / "image/train" / f"MPSC_img_{img_id}.jpg"))
        img = cache[img_id]
        if img is None:
            continue
        crop = rotate_crop(img, np.reshape(coords, (4, 2)))
        if min(crop.shape[:2]) < 8:
            continue
        name = f"images/{tag}/{img_id}_{k}.jpg"
        cv2.imwrite(str(out_part / name), crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
        lines.append(f"{name}\t{text}")
    return lines


def pac_annotations():
    for ann_path in sorted((ROOT / "data/annotations").glob("pac_handwriting_*.json")):
        ann = json.loads(ann_path.read_text(encoding="utf-8"))
        img = cv2.imread(str(ROOT / "data/raw" / ann["image"]))
        if img is not None:
            yield ann_path.stem, img, [t for t in ann["texts"] if t.get("bbox")]


def add_pac(out_part: Path, margin: float = 0.1) -> list[str]:
    """운영측 손글씨 줄을 사람이 그린 상자(10% 여백)로 자름 — eval_handwriting.py --pac 과 같음"""
    (out_part / "images").mkdir(parents=True, exist_ok=True)
    lines = []
    for stem, img, texts in pac_annotations():
        for i, t in enumerate(texts):
            x1, y1, x2, y2 = t["bbox"]
            mx, my = (x2 - x1) * margin, (y2 - y1) * margin
            crop = img[max(0, int(y1 - my)):int(y2 + my), max(0, int(x1 - mx)):int(x2 + mx)]
            name = f"images/{stem}_{i}.png"
            cv2.imwrite(str(out_part / name), crop)
            lines.append(f"{name}\t{t['text']}")
    return lines


def add_pac_det(out_part: Path, det_dir: str) -> list[str]:
    """운영측 손글씨 사진을 1단계처럼 키워(vision.preprocess) 검출기로 잡은 상자를 PaddleOCR 처럼 잘라 냄.
    상자 중심이 정답 상자 하나 안에만 있을 때 그 정답을 붙임. 검출 상자가 아래 줄까지 걸쳐 잡는 경우가 많아(예시 1·2의 F 줄이
    V 줄 상자의 60~70%를 덮음) 그대로 둠 — 1단계가 인식기에 실제로 넘기는 모양이고, 인식기는 그 줄의 글자를 읽어야 함"""
    from paddleocr import TextDetection

    from vision.ocr import DEFAULT_CONFIG as c
    from vision.preprocess import preprocess

    model = TextDetection(model_name=c.det_model, model_dir=det_dir, limit_side_len=c.det_limit_side_len,
                          limit_type=c.det_limit_type, enable_mkldnn=False)
    (out_part / "images").mkdir(parents=True, exist_ok=True)
    lines, spill, extra = [], 0, 0
    for stem, img, texts in pac_annotations():
        big, _, to_original = preprocess(img)
        s = 1 / to_original[0, 0]
        boxes = [[v * s for v in t["bbox"]] for t in texts]
        for k, poly in enumerate(list(model.predict(big))[0]["dt_polys"]):
            cx, cy = np.asarray(poly, float).mean(0)
            inside = [i for i, (x1, y1, x2, y2) in enumerate(boxes) if x1 <= cx <= x2 and y1 <= cy <= y2]
            mask = cv2.fillPoly(np.zeros(big.shape[:2], np.uint8), [np.asarray(poly, np.int32)], 1)
            covered = [i for i, (x1, y1, x2, y2) in enumerate(boxes)  # 정답 상자 넓이의 절반 넘게 덮음 (기울어진 상자 그대로)
                       if mask[int(y1):int(y2), int(x1):int(x2)].mean() > 0.5]
            if len(inside) != 1:
                extra += 1
                continue
            spill += bool(set(covered) - set(inside))
            name = f"images/{stem}_det{k}.png"
            cv2.imwrite(str(out_part / name), rotate_crop(big, min_area_quad(poly)))
            lines.append(f"{name}\t{texts[inside[0]]['text']}")
    print(f"pac_rec_det: 정답 줄에 붙인 상자 {len(lines)}개 (그중 다른 줄 상자를 절반 넘게 덮은 것 {spill}개), 정답 밖 상자 {extra}개")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--synth", type=Path, action="append", default=[], help="학습용 합성 줄 폴더 (여러 번)")
    parser.add_argument("--synth-val", type=Path, action="append", default=[], help="평가용 합성 줄 폴더 (여러 번)")
    parser.add_argument("--steel-train", type=Path)
    parser.add_argument("--steel-repeat", type=int, default=4, help="steel-ocr 학습 글자가 349개뿐이라 반복")
    parser.add_argument("--steel-val", type=Path, action="append", default=[])
    parser.add_argument("--mpsc-train", type=Path, help="MPSC 폴더 (annotation/train · image/train)")
    parser.add_argument("--mpsc-max", type=int, default=8000)
    parser.add_argument("--pac", action="store_true")
    parser.add_argument("--pac-det", help="검출 모델 폴더 — 운영측 손글씨를 이 검출기로 잘라 pac_rec_det 을 만듦")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    out, rng = args.out, np.random.default_rng(args.seed)
    train = []
    for i, src in enumerate(args.synth):
        train += copy_lines(src, out / "rec_train", f"synth{i}")
    if args.steel_train:
        train += copy_steel(args.steel_train, out / "rec_train", "steel", args.steel_repeat)
    if args.mpsc_train:
        train += add_mpsc(args.mpsc_train, out / "rec_train", "mpsc", args.mpsc_max, rng)
    rng.shuffle(train)
    write_part(out, "rec_train", train)
    select = []
    for part, items in (("rec_val", [copy_lines(src, out / "rec_val", f"synth{i}") for i, src in enumerate(args.synth_val)]),
                        ("steel_rec_val", [copy_steel(f, out / "steel_rec_val", "steel") for f in args.steel_val])):
        lines = [line for chunk in items for line in chunk]
        if lines:
            write_part(out, part, lines)
            select += [f"{part}/{line}" for line in lines]
    if select:
        (out / "val_select.tsv").write_text("\n".join(select) + "\n", encoding="utf-8")
        print(f"val_select.tsv: {len(select)}줄")
    if args.pac:
        write_part(out, "pac_rec", add_pac(out / "pac_rec"))
    if args.pac_det:
        write_part(out, "pac_rec_det", add_pac_det(out / "pac_rec_det", args.pac_det))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
