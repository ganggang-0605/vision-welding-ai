"""정답 데이터 점검: 형식 오류·사진 누락·사전에 없는 기호 확인, split 자동 배정, 통계 출력

사용: backend/.venv/bin/python vision/tools/check_dataset.py [--workspace demo]
형식 설명: data/annotations/README.md
"""
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
ANN_DIR = ROOT / "data" / "annotations"
SEED_WORKSPACES = ROOT / "data" / "seed" / "workspaces"

EVAL_RATIO = 0.2
STYLES = {"stamped", "stencil", "handwritten", "printed"}
CONDITIONS = {"dark", "glare", "curved", "skewed", "stain", "scratch", "blur"}


def assign_split(image_name: str) -> str:
    """파일 이름 해시로 정해서 누가 돌려도 같은 결과"""
    h = int(hashlib.sha1(image_name.encode("utf-8")).hexdigest(), 16)
    return "eval" if (h % 1000) / 1000 < EVAL_RATIO else "train"


def check_bbox(bbox, size, where: str, errors: list[str]) -> None:
    if bbox is None:
        return
    if not (isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(v, (int, float)) for v in bbox)):
        errors.append(f"{where}: bbox는 [x1, y1, x2, y2] 숫자 4개여야 함")
        return
    x1, y1, x2, y2 = bbox
    if not (x1 < x2 and y1 < y2):
        errors.append(f"{where}: bbox 좌상단이 우하단보다 작아야 함")
    if size and (x1 < 0 or y1 < 0 or x2 > size[0] or y2 > size[1]):
        errors.append(f"{where}: bbox가 사진 크기 {size[0]}x{size[1]}를 벗어남")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="demo", help="기호 label을 대조할 워크스페이스 (data/seed/workspaces/<id>)")
    args = parser.parse_args()
    symbol_dict = SEED_WORKSPACES / args.workspace / "symbol_dictionary.json"
    symbol_codes = {e["code"] for e in json.loads(symbol_dict.read_text(encoding="utf-8"))["entries"]}
    files = sorted(ANN_DIR.glob("*.json"))
    if not files:
        print(f"정답 파일이 없습니다: {ANN_DIR}")
        return 0

    errors: list[str] = []
    warnings: list[str] = []
    stats = {"split": Counter(), "style": Counter(), "condition": Counter(), "symbol": Counter()}
    n_texts = n_text_bbox = n_symbols = 0

    for path in files:
        try:
            ann = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"{path.name}: JSON 형식 오류 ({e})")
            continue

        image_name = ann.get("image")
        if not image_name:
            errors.append(f"{path.name}: image 필드 없음")
            continue
        if Path(image_name).stem != path.stem:
            warnings.append(f"{path.name}: 파일 이름과 image({image_name})가 다름")

        size = None
        image_path = RAW_DIR / image_name
        if image_path.exists():
            with Image.open(image_path) as im:
                size = im.size
        else:
            errors.append(f"{path.name}: 사진 없음 ({image_path.relative_to(ROOT)})")

        for c in ann.get("conditions", []):
            if c not in CONDITIONS:
                warnings.append(f"{path.name}: 알 수 없는 촬영 조건 '{c}'")
            stats["condition"][c] += 1

        for i, t in enumerate(ann.get("texts", [])):
            where = f"{path.name} texts[{i}]"
            if not t.get("text"):
                errors.append(f"{where}: text 비어 있음")
            if t.get("style") not in STYLES:
                errors.append(f"{where}: style은 {sorted(STYLES)} 중 하나")
            check_bbox(t.get("bbox"), size, where, errors)
            stats["style"][t.get("style")] += 1
            n_texts += 1
            n_text_bbox += t.get("bbox") is not None

        for i, s in enumerate(ann.get("symbols", [])):
            where = f"{path.name} symbols[{i}]"
            if s.get("label") not in symbol_codes:
                warnings.append(f"{where}: 기호 사전에 없는 label '{s.get('label')}'")
            check_bbox(s.get("bbox"), size, where, errors)
            stats["symbol"][s.get("label")] += 1
            n_symbols += 1

        if ann.get("split") not in ("train", "eval"):
            ann["split"] = assign_split(image_name)
            path.write_text(json.dumps(ann, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        stats["split"][ann["split"]] += 1

    print(f"사진 {len(files)}장 · 표기 {n_texts}개 (위치 있음 {n_text_bbox}) · 기호 {n_symbols}개")
    for key, counter in stats.items():
        if counter:
            print(f"  {key}: " + ", ".join(f"{k} {v}" for k, v in counter.most_common()))
    for w in warnings:
        print(f"[주의] {w}")
    for e in errors:
        print(f"[오류] {e}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
