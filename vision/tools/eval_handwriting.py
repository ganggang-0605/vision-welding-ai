"""손글씨 각장 표기(F·V·S + 숫자) 인식 평가: 합성 손글씨(정답 있음) + 운영측 예시(정답 없음, 예측만)

인식기 (--model, 여러 번 가능):
  paddle                    PaddleOCR 인식 모델 (vision.ocr.DEFAULT_CONFIG.rec_model)
  trocr:<Hugging Face 모델>  예: trocr:microsoft/trocr-base-handwritten
  parseq:<변형>[@가중치]     예: parseq:parseq_tiny, parseq:parseq_tiny@$OUT/parseq_tiny_hw.pt (train_handwriting.py 결과)
점수는 두 가지: raw(인식기 출력 그대로) · format(vision.marking.to_marking 으로 각장 형식에 맞춘 것).
TrOCR은 --constrain 을 주면 디코딩 단계에서 각장 형식만 나오게 제한한 결과(constrained)도 냄.

사용:
  python vision/tools/eval_handwriting.py --data data/synth/hw_eval --model paddle \\
      --model trocr:microsoft/trocr-base-handwritten --constrain --pac --out $OUT/hw_baseline.json
  --pac : data/annotations/pac_handwriting_*.json 의 글자 상자로 운영측 예시를 잘라 평가 (정답 = 정답 파일의 text)
  --export DIR : 운영측 손글씨를 평가 세트로 내보내기만 함 (Colab 학습 뒤 평가용, 모델 불필요)
      DIR/pac_rec/{images, labels.tsv} — 글자 줄 (인식 평가), DIR/pac_det/{images, det_labels.txt} — 사진 (검출 평가)
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from vision.marking import CHARSET, PATTERN, to_marking

ROOT = Path(__file__).resolve().parents[2]
PREFIX = re.compile(r"([FVS](\d{1,2}(\.\d?)?)?)?")


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def load_lines(data_dir: Path, limit: int | None) -> list[tuple[str, np.ndarray, str]]:
    rows = []
    for line in (data_dir / "labels.tsv").read_text(encoding="utf-8").splitlines()[:limit]:
        rel, label = line.split("\t")
        rows.append((rel, cv2.imread(str(data_dir / rel)), label))
    return rows


def load_pac(margin: float = 0.1) -> list[tuple[str, np.ndarray, str]]:
    """운영측 손글씨 예시를 정답 파일의 글자 상자로 자름 → (id, 이미지, 정답).
    정답은 사람이 읽은 값 — 예시 1·3의 F 뒤 꼬리 획은 F의 일부로 보고 F5.5 (vision/reports 참고)"""
    rows = []
    for ann_path in sorted((ROOT / "data/annotations").glob("pac_handwriting_*.json")):
        ann = json.loads(ann_path.read_text(encoding="utf-8"))
        img = cv2.imread(str(ROOT / "data/raw" / ann["image"]))
        if img is None:
            continue
        for i, t in enumerate(ann["texts"]):
            x1, y1, x2, y2 = t["bbox"]
            mx, my = (x2 - x1) * margin, (y2 - y1) * margin
            crop = img[max(0, int(y1 - my)):int(y2 + my), max(0, int(x1 - mx)):int(x2 + mx)]
            rows.append((f"{ann_path.stem}#{i}", crop, t["text"]))
    return rows


# ── 인식기: 이미지 목록 → [(글자, 확률)] ──

class Paddle:
    def __init__(self, _: str):
        from paddleocr import TextRecognition

        from vision.ocr import DEFAULT_CONFIG

        self.model = TextRecognition(model_name=DEFAULT_CONFIG.rec_model, model_dir=DEFAULT_CONFIG.rec_model_dir, enable_mkldnn=False)

    def read(self, images, constrain=False):
        return [(r["rec_text"], float(r["rec_score"])) for r in self.model.predict(images, batch_size=16)]


class TrOCR:
    def __init__(self, name: str):
        import torch
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel

        self.torch = torch
        self.proc = TrOCRProcessor.from_pretrained(name)
        self.model = VisionEncoderDecoderModel.from_pretrained(name).eval()
        tok = self.proc.tokenizer
        self.pieces = {}
        for i in range(len(tok)):
            t = tok.decode([i]).strip()
            if t and " " not in t and all(c in CHARSET for c in t):
                self.pieces[i] = t
        self.eos = self.model.generation_config.eos_token_id or tok.eos_token_id
        self.skip = {self.model.generation_config.decoder_start_token_id, tok.bos_token_id}

    def _allowed(self, batch_id, ids):
        prefix = "".join(self.pieces.get(int(i), "") for i in ids.tolist() if int(i) not in self.skip)
        ok = [i for i, t in self.pieces.items() if PREFIX.fullmatch(prefix + t)]
        if PATTERN.fullmatch(prefix):
            ok.append(self.eos)
        return ok or [self.eos]

    def read(self, images, constrain=False):
        from PIL import Image

        out = []
        for i in range(0, len(images), 8):
            batch = [Image.fromarray(cv2.cvtColor(im, cv2.COLOR_BGR2RGB)) for im in images[i:i + 8]]
            pixels = self.proc(images=batch, return_tensors="pt").pixel_values
            kwargs = {"prefix_allowed_tokens_fn": self._allowed} if constrain else {}
            with self.torch.no_grad():
                gen = self.model.generate(pixels, max_new_tokens=12, num_beams=4, output_scores=True,
                                          return_dict_in_generate=True, **kwargs)
            texts = self.proc.batch_decode(gen.sequences, skip_special_tokens=True)
            probs = gen.sequences_scores.exp().tolist()
            out += [(t.replace(" ", "") if constrain else t, p) for t, p in zip(texts, probs)]
        return out


class Parseq:
    def __init__(self, spec: str):
        import torch

        variant, _, weights = spec.partition("@")
        self.torch = torch
        self.model = torch.hub.load("baudm/parseq", variant, pretrained=True, trust_repo=True).eval()
        if weights:
            self.model.load_state_dict(torch.load(weights, map_location="cpu"))
        tok = self.model.tokenizer
        allowed = [tok._stoi[c] for c in CHARSET if c in tok._stoi] + [tok._stoi[tok.EOS]]
        self.mask = torch.full((len(tok._itos),), float("-inf"))
        self.mask[allowed] = 0
        self.size = tuple(self.model.hparams.img_size)  # (높이, 폭)

    def read(self, images, constrain=False):
        torch = self.torch
        out = []
        for i in range(0, len(images), 32):
            batch = []
            for im in images[i:i + 32]:
                rgb = cv2.cvtColor(cv2.resize(im, self.size[::-1], interpolation=cv2.INTER_CUBIC), cv2.COLOR_BGR2RGB)
                batch.append(torch.from_numpy(rgb).permute(2, 0, 1).float().div(255).sub(0.5).div(0.5))
            with torch.no_grad():
                logits = self.model(torch.stack(batch))
            if constrain:
                logits = logits + self.mask[: logits.shape[-1]]
            labels, confs = self.model.tokenizer.decode(logits.softmax(-1))
            out += [(t, float(c.prod())) for t, c in zip(labels, confs)]
        return out


def make(spec: str):
    kind, _, name = spec.partition(":")
    return {"paddle": Paddle, "trocr": TrOCR, "parseq": Parseq}[kind](name)


def score(preds: list[str], labels: list[str]) -> dict:
    chars = sum(len(l) for l in labels)
    return {
        "exact": round(sum(p == l for p, l in zip(preds, labels)) / len(labels), 4),
        "cer": round(sum(min(edit_distance(p, l), len(l)) for p, l in zip(preds, labels)) / chars, 4),
        "letter": round(sum(p[:1] == l[:1] for p, l in zip(preds, labels)) / len(labels), 4),
        "format_valid": round(sum(bool(PATTERN.fullmatch(p)) for p in preds) / len(labels), 4),
    }


def export_pac(out: Path) -> None:
    """운영측 손글씨를 PaddleOCR 학습·평가 형식으로 내보냄 (인식: 글자 줄, 검출: 사진 + 상자)"""
    rec, det = out / "pac_rec", out / "pac_det"
    (rec / "images").mkdir(parents=True, exist_ok=True)
    (det / "images").mkdir(parents=True, exist_ok=True)
    rec_lines = []
    for i, (rid, crop, label) in enumerate(load_pac()):
        name = f"images/{rid.replace('#', '_')}.png"
        cv2.imwrite(str(rec / name), crop)
        rec_lines.append(f"{name}\t{label}")
    (rec / "labels.tsv").write_text("\n".join(rec_lines) + "\n", encoding="utf-8")
    det_lines = []
    for ann_path in sorted((ROOT / "data/annotations").glob("pac_handwriting_*.json")):
        ann = json.loads(ann_path.read_text(encoding="utf-8"))
        img = cv2.imread(str(ROOT / "data/raw" / ann["image"]))
        name = f"images/{ann_path.stem}.png"
        cv2.imwrite(str(det / name), img)
        boxes = [{"transcription": t["text"], "points": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]}
                 for t in ann["texts"] for x1, y1, x2, y2 in [t["bbox"]]]
        det_lines.append(f"{name}\t{json.dumps(boxes, ensure_ascii=False)}")
    (det / "det_labels.txt").write_text("\n".join(det_lines) + "\n", encoding="utf-8")
    print(f"운영측 손글씨 → {rec} (글자 줄 {len(rec_lines)}개), {det} (사진 {len(det_lines)}장)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, action="append", default=[], help="labels.tsv 가 있는 폴더")
    parser.add_argument("--model", action="append", default=[])
    parser.add_argument("--constrain", action="store_true", help="TrOCR·PARSeq 출력을 각장 형식 글자로 제한")
    parser.add_argument("--pac", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--export", type=Path)
    args = parser.parse_args()
    if args.export:
        export_pac(args.export)
        return 0
    if not args.model:
        parser.error("--model 이 필요함 (또는 --export)")

    sets = {d.name: load_lines(d, args.limit) for d in args.data}
    pac = load_pac() if args.pac else []
    report = {"models": {}}
    for spec in args.model:
        try:
            rec = make(spec)
        except Exception as e:  # 모델 받기·불러오기 실패는 기록만 하고 다음 모델로
            report["models"][spec] = {"error": repr(e)}
            print(f"[{spec}] 불러오기 실패: {e!r}", file=sys.stderr)
            continue
        modes = ["raw"] + (["constrained"] if args.constrain and not isinstance(rec, Paddle) else [])
        res = {}
        for name, rows in sets.items():
            labels, images = [r[2] for r in rows], [r[1] for r in rows]
            res[name] = {}
            for mode in modes:
                start = time.perf_counter()
                out = rec.read(images, constrain=mode == "constrained")
                sec = (time.perf_counter() - start) / max(1, len(images))
                texts = [t for t, _ in out]
                formatted = [to_marking(t) or "" for t in texts]
                res[name][mode] = {"score": score(texts, labels), "score_format": score(formatted, labels),
                                   "sec_per_line": round(sec, 4),
                                   "details": [{"id": r[0], "label": r[2], "pred": t, "prob": round(p, 4), "format": f}
                                               for r, (t, p), f in zip(rows, out, formatted)]}
                print(f"[{spec}] {name} {mode}: {res[name][mode]['score']} → 형식 후처리 {res[name][mode]['score_format']}"
                      f" ({sec:.3f}초/줄)")
        if pac:
            res["pac"] = {}
            for mode in modes:
                out = rec.read([r[1] for r in pac], constrain=mode == "constrained")
                texts = [t for t, _ in out]
                res["pac"][mode] = {
                    "score": score(texts, [r[2] for r in pac]),
                    "score_format": score([to_marking(t) or "" for t in texts], [r[2] for r in pac]),
                    "details": [{"id": r[0], "label": r[2], "pred": t, "prob": round(p, 4), "format": to_marking(t)}
                                for r, (t, p) in zip(pac, out)],
                }
                print(f"[{spec}] 운영측 {mode}: {res['pac'][mode]['score_format']} — " + " | ".join(
                    f"{d['label']}→{d['pred']}({d['prob']:.2f})" for d in res["pac"][mode]["details"]))
        report["models"][spec] = res
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
