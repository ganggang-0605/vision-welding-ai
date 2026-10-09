"""유사 문자 후보: 확률이 낮은 글자 줄을 인식 모델로 한 번 더 읽어, 글자 칸마다의 확률(CTC 출력)로 2·3순위 읽기를 찾음

PaddleOCR 은 칸마다 가장 높은 글자만 이어 붙인 한 가지 읽기(P-1O)만 돌려주지만, 모델 출력에는 칸마다 다른 글자의 확률도
있음(O 0.6 · 0 0.4). 이 확률표에서 빔 탐색으로 확률이 높은 읽기 몇 개를 뽑아 candidates 로 붙임 → 2단계가 후보까지
DB와 대조하고(P-1O 는 조립 트리에 없지만 P-10 은 있음), 작업자 확인 화면이 "1순위 5.5 (78%), 2순위 t.5 (22%)"처럼 보여 줌.
후보의 prob 는 뽑은 후보끼리 나눈 비율 (합 1) — 첫 번째는 1단계가 고른 읽기(text)
"""
from collections import defaultdict
from functools import lru_cache

import numpy as np


def min_area_quad(poly) -> np.ndarray:
    """검출 다각형 → 가장 작은 회전 사각형 4점 (왼쪽 위부터 시계 방향, PaddleOCR get_minarea_rect 와 같음)"""
    import cv2

    box = sorted(cv2.boxPoints(cv2.minAreaRect(np.asarray(poly, np.float32))).tolist(), key=lambda p: p[0])
    left, right = sorted(box[:2], key=lambda p: p[1]), sorted(box[2:], key=lambda p: p[1])
    return np.float32([left[0], right[0], right[1], left[1]])


def rotate_crop(img: np.ndarray, quad) -> np.ndarray:
    """기울어진 사각형을 펴서 자름 (세로로 긴 건 90° 돌림) — PaddleOCR 이 인식기에 넘기는 것과 같은 방식"""
    import cv2

    pts = np.asarray(quad, np.float32)
    w = int(max(np.linalg.norm(pts[0] - pts[1]), np.linalg.norm(pts[2] - pts[3])))
    h = int(max(np.linalg.norm(pts[0] - pts[3]), np.linalg.norm(pts[1] - pts[2])))
    dst = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    crop = cv2.warpPerspective(img, cv2.getPerspectiveTransform(pts, dst), (w, h),
                               borderMode=cv2.BORDER_REPLICATE, flags=cv2.INTER_CUBIC)
    return np.rot90(crop) if h and h / max(w, 1) >= 1.5 else crop


def ctc_beam_search(probs: np.ndarray, charset: list[str], beam: int = 8, top_chars: int = 4,
                    min_prob: float = 1e-3) -> list[tuple[str, float]]:
    """CTC 확률표(칸 × 글자, 0번 = 빈칸) → [(읽기, 확률)] 확률 내림차순. 같은 읽기가 되는 여러 칸 배치의 확률을 더함
    (prefix beam search). 칸마다 확률 상위 top_chars 글자(min_prob 이상)만 봄. 확률은 칸마다 다시 맞춘 상대값"""
    beams: dict[tuple, list[float]] = {(): [1.0, 0.0]}  # 읽기 → [빈칸으로 끝난 확률, 글자로 끝난 확률]
    for row in probs:
        chars = [int(c) for c in np.argsort(row)[::-1][:top_chars] if row[c] >= min_prob or c == 0]
        nxt: dict[tuple, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for prefix, (p_blank, p_char) in beams.items():
            for c in chars:
                p = float(row[c])
                if c == 0:
                    nxt[prefix][0] += (p_blank + p_char) * p
                elif prefix and prefix[-1] == c:
                    nxt[prefix + (c,)][1] += p_blank * p  # 빈칸을 사이에 둔 같은 글자 = 두 글자
                    nxt[prefix][1] += p_char * p  # 이어진 같은 글자 = 한 글자
                else:
                    nxt[prefix + (c,)][1] += (p_blank + p_char) * p
        top = sorted(nxt.items(), key=lambda kv: -sum(kv[1]))[:beam]
        scale = sum(top[0][1]) or 1.0  # 칸이 길어도 0으로 수렴하지 않게
        beams = {k: [v[0] / scale, v[1] / scale] for k, v in top}
    return sorted((("".join(charset[c] for c in prefix), sum(p)) for prefix, p in beams.items()), key=lambda x: -x[1])


class _Probe:
    """인식 모델 하나 + 확률표 가로채기 (PaddleOCR 결과에는 확률표가 없어서 후처리 직전에 받아 둠)"""

    def __init__(self, model_name: str, model_dir: str | None):
        from paddleocr import TextRecognition

        self.model = TextRecognition(model_name=model_name, model_dir=model_dir, enable_mkldnn=False)
        predictor = self.model.paddlex_predictor
        decoder = predictor.post_op
        self.charset = list(decoder.character)
        self.last: np.ndarray | None = None

        def capture(pred, **kwargs):
            self.last = np.array(pred[0])[0]
            return decoder(pred, **kwargs)

        predictor.post_op = capture

    def read(self, crop: np.ndarray) -> tuple[str, np.ndarray]:
        result = list(self.model.predict(np.ascontiguousarray(crop)))[0]
        return result["rec_text"], self.last


@lru_cache(maxsize=2)
def _probe(model_name: str, model_dir: str | None) -> _Probe:
    return _Probe(model_name, model_dir)


def line_candidates(probe: _Probe, image: np.ndarray, detection: dict, max_n: int = 3,
                    min_share: float = 0.02) -> list[dict] | None:
    """글자 줄 하나의 후보 [{text, prob}] (첫 번째 = detection text). 다시 읽은 결과가 1단계 읽기와 다르면
    (뒤집힌 줄로 판단해 돌려 읽었거나, 여러 줄을 함께 읽어 조금 달라짐) 180° 돌려 한 번 더 보고, 그래도 다르면 None"""
    text = detection["text"]
    crop = rotate_crop(image, min_area_quad(detection["polygon"]))
    for img in (crop, np.rot90(crop, 2)):
        read, probs = probe.read(img)
        if read.strip() == text:
            break
    else:
        return None
    merged: dict[str, float] = {}
    for reading, p in ctc_beam_search(probs, probe.charset):
        if reading.strip():
            merged[reading.strip()] = merged.get(reading.strip(), 0.0) + p
    if text not in merged:
        return None
    others = sorted(((t, p) for t, p in merged.items() if t != text), key=lambda x: -x[1])[:max_n - 1]
    picked = [(text, merged[text])] + others
    total = sum(p for _, p in picked)
    out = [{"text": t, "prob": round(p / total, 4)} for t, p in picked]
    out = out[:1] + [c for c in out[1:] if c["prob"] >= min_share]
    return out if len(out) > 1 else None


def add_candidates(image: np.ndarray, detections: list[dict], model_name: str, model_dir: str | None,
                   below: float, max_n: int) -> list[dict]:
    """확률이 below 보다 낮은 글자 줄에만 candidates 를 붙임 (image = 1단계가 OCR 에 넣은 이미지, 좌표도 그 기준)"""
    low = [d for d in detections if d["prob"] < below and d.get("polygon")]
    if not low:
        return detections
    probe = _probe(model_name, model_dir)
    out = []
    for d in detections:
        cands = line_candidates(probe, image, d, max_n) if d in low else None
        out.append({**d, "candidates": cands} if cands else d)
    return out
