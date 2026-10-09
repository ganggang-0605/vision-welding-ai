"""손글씨 각장 표기(F·V·S + 숫자) 합성: 정답을 알고 만드는 학습·평가 데이터

운영측 손글씨 예시(data/annotations/pac_handwriting_*.json)의 특징을 흉내냄:
- 글씨 버릇(stroke 글씨체): F는 세로획이 위아래로 길고 가운데 가로획이 아래로 꺾인 꼬리가 붙기도 함 (숫자가 아님 —
  예시 1·3의 F5.5), 5는 ʃ에 가로획을 걸치거나 <에 가로획, V는 U처럼 둥글게, 숫자 없이 V만 쓴 줄, 소수점 뒤 숫자는 작음
- 철판 위 분필·석필 흰 글씨 (흰 철판 위 흐린 흰 글씨 포함), 글자에 붙은 화살표(왼쪽·오른쪽)·꼬리 선·용접선,
  두세 줄로 쌓아 쓰기(F5.5 / V / S6.5), 가로 178px 정도의 흐린 사진

두 가지를 만듦 (--mode):
- lines : 글자 줄 이미지 + labels.tsv ("images/00000.jpg<TAB>F5.5") — 인식기 학습 (PaddleOCR 인식 학습 형식과 같음)
- scenes: 철판 한 장에 표기 묶음 여러 개 + det_labels.txt (PaddleOCR 검출 학습 형식:
  "images/00000.jpg<TAB>[{"transcription": "F5.5", "points": [[x, y] × 4]}]") — 검출기 학습
글씨체(--styles): stroke(운영측 버릇, --stroke-ratio 비율) + Hershey 한 획 글꼴 + --fonts TTF.
처음 보는 글씨에도 통하는지 보려고 Hershey·TTF는 학습용(train)과 평가용(eval)을 겹치지 않게 나눔.
배경은 철판 질감을 만들어 씀 (--backgrounds 로 사진을 줄 수도 있지만 글자가 없는 사진만 — 배경 글자가 정답과 섞임).

사용:
  python vision/tools/synth_handwriting.py --mode lines --out data/synth/rec_train --n 20000 --styles train --fonts '...'
  python vision/tools/synth_handwriting.py --mode scenes --out data/synth/det_train --n 2000 --styles train --fonts '...'
"""
import argparse
import glob
import json
from pathlib import Path

import cv2
import numpy as np

# Hershey 글꼴: 학습용과 평가용을 겹치지 않게 나눔
HERSHEY = {
    "train": [cv2.FONT_HERSHEY_SIMPLEX, cv2.FONT_HERSHEY_PLAIN, cv2.FONT_HERSHEY_DUPLEX, cv2.FONT_HERSHEY_SCRIPT_SIMPLEX],
    "eval": [cv2.FONT_HERSHEY_COMPLEX, cv2.FONT_HERSHEY_SCRIPT_COMPLEX, cv2.FONT_HERSHEY_TRIPLEX],
}

# 운영측 글씨 버릇을 흉내 낸 한 획 글자: 글자마다 모양 후보 여러 개, 후보 = 획 목록, 획 = 점 목록
# 좌표는 글자 높이 1 기준 (y 0 = 글자 위, 1 = 글자 아래 기준선), x는 글자 폭 1 기준. 위아래로 넘쳐도 됨
STROKES = {
    "F": [[[(0.25, -0.25), (0.27, 0.5), (0.25, 1.15)], [(0.25, 0.05), (0.9, 0.0)], [(0.0, 0.5), (0.75, 0.45)]],
          [[(0.2, 0.0), (0.2, 1.0)], [(0.2, 0.0), (0.85, 0.0)], [(0.2, 0.48), (0.7, 0.48)]]],
    "V": [[[(0.05, 0.0), (0.1, 0.6), (0.45, 1.0), (0.85, 0.6), (0.9, 0.0)]],  # U처럼 둥근 V
          [[(0.05, 0.0), (0.45, 1.0), (0.9, 0.0)]]],
    "S": [[[(0.85, 0.12), (0.55, 0.0), (0.15, 0.15), (0.25, 0.45), (0.7, 0.55), (0.85, 0.85), (0.45, 1.0), (0.05, 0.85)]],
          [[(0.8, 0.0), (0.3, 0.2), (0.35, 0.5), (0.75, 0.62), (0.5, 1.0), (0.1, 0.9)]]],
    "5": [[[(0.85, 0.0), (0.25, 0.0)], [(0.25, 0.0), (0.2, 0.45), (0.6, 0.38), (0.85, 0.65), (0.6, 1.0), (0.1, 0.9)]],
          [[(0.8, -0.15), (0.55, 0.15), (0.45, 0.55), (0.35, 0.9), (0.15, 1.05), (0.05, 0.95)], [(0.15, 0.3), (0.95, 0.25)]],  # ʃ + 가로획
          [[(0.3, 0.05), (0.95, 0.05)], [(0.75, 0.05), (0.1, 0.55), (0.7, 1.0)]]],  # < + 가로획
    "0": [[[(0.45 + 0.38 * np.sin(t), 0.5 - 0.5 * np.cos(t)) for t in np.linspace(0, 2 * np.pi, 13)]]],
    "1": [[[(0.3, 0.2), (0.55, 0.0), (0.5, 1.0)]], [[(0.5, 0.0), (0.45, 1.0)]]],
    "2": [[[(0.15, 0.25), (0.45, 0.0), (0.8, 0.15), (0.75, 0.4), (0.1, 1.0), (0.9, 1.0)]]],
    "3": [[[(0.15, 0.1), (0.5, 0.0), (0.8, 0.2), (0.45, 0.48), (0.85, 0.7), (0.55, 1.0), (0.1, 0.9)]]],
    "4": [[[(0.65, 1.05), (0.65, 0.0), (0.05, 0.65), (0.9, 0.65)]]],
    "6": [[[(0.75, 0.05), (0.35, 0.3), (0.15, 0.7), (0.35, 1.0), (0.7, 0.9), (0.75, 0.62), (0.4, 0.52), (0.18, 0.7)]]],
    "7": [[[(0.05, 0.0), (0.9, 0.0), (0.4, 1.0)]]],
    "8": [[[(0.5, 0.48), (0.2, 0.3), (0.3, 0.02), (0.7, 0.02), (0.8, 0.3), (0.5, 0.48), (0.15, 0.75), (0.35, 1.0),
            (0.7, 1.0), (0.85, 0.75), (0.5, 0.48)]]],
    "9": [[[(0.8, 0.3), (0.5, 0.0), (0.2, 0.2), (0.3, 0.5), (0.75, 0.4), (0.8, 0.3), (0.7, 1.0)]]],
}
F_TAIL = [(0.0, 0.5), (0.75, 0.45), (0.55, 1.0)]  # 가운데 가로획이 아래로 꺾인 꼬리 (예시 1·3)
MIN_GAP = 30  # 글씨와 배경 밝기 차이 하한 — 예시 2(흰 철판 위 흐린 흰 글씨)처럼 흐리되 사람은 읽을 수 있게


def random_label(rng: np.random.Generator) -> str:
    """각장 표기: 대부분 4~8mm의 .0·.5 (운영측 예시가 5.0~6.5), 가끔 다른 값·정수·글자만"""
    letter = str(rng.choice(list("FVS"), p=[0.5, 0.25, 0.25]))
    r = rng.random()
    if r < 0.05:
        return "V" if rng.random() < 0.7 else letter  # 숫자 없이 글자만 (예시 1·3의 V)
    if r < 0.10:
        return f"{letter}{int(rng.integers(3, 13))}"
    if r < 0.85:
        return f"{letter}{rng.choice(np.arange(4.0, 8.01, 0.5)):.1f}"
    if r < 0.95:
        return f"{letter}{rng.choice(np.arange(3.0, 12.51, 0.5)):.1f}"
    return f"{letter}{int(rng.integers(3, 13))}.{int(rng.integers(0, 10))}"


# ── 글자 하나 그리기: (마스크, 글자 위 기준 세로 위치) ──

def chaikin(points: np.ndarray, iters: int = 2) -> np.ndarray:
    """꺾인 선을 부드럽게 (손으로 쓴 곡선처럼)"""
    for _ in range(iters):
        if len(points) < 3:
            return points
        q = 0.75 * points[:-1] + 0.25 * points[1:]
        r = 0.25 * points[:-1] + 0.75 * points[1:]
        points = np.vstack([points[:1], np.column_stack([q, r]).reshape(-1, 2), points[-1:]])
    return points


def glyph_stroke(ch: str, height: int, thickness: int, rng: np.random.Generator) -> tuple[np.ndarray, int]:
    strokes = [list(s) for s in STROKES[ch][int(rng.integers(len(STROKES[ch])))]]
    if ch == "F" and len(strokes) == 3 and rng.random() < 0.5:
        strokes[2] = F_TAIL
    width = height * rng.uniform(0.5, 0.8)
    pad = int(height * 0.5) + thickness
    canvas = np.zeros((int(height * 2) + 2 * pad, int(width * 1.6) + 2 * pad), np.uint8)
    for s in strokes:
        pts = np.asarray(s, np.float64) + rng.normal(0, 0.045, (len(s), 2))
        pts = chaikin(pts) * [width, height] + [pad + 0.3 * width, pad + 0.4 * height]
        cv2.polylines(canvas, [np.round(pts).astype(np.int32)], False, 255, thickness, cv2.LINE_AA)
    ys, xs = np.nonzero(canvas > 20)
    top = ys.min() - (pad + 0.4 * height)  # 글자 위(y 0)에서 마스크 위까지 — F 세로획처럼 위로 넘치면 음수
    return canvas[ys.min():ys.max() + 1, xs.min():xs.max() + 1], int(round(top))


def glyph_hershey(ch: str, font: int, height: int, thickness: int, italic: bool) -> np.ndarray:
    scale = height / 22.0
    face = font | (cv2.FONT_ITALIC if italic else 0)
    (w, h), base = cv2.getTextSize(ch, face, scale, thickness)
    canvas = np.zeros((h + base + 2 * thickness + 4, w + 2 * thickness + 4), np.uint8)
    cv2.putText(canvas, ch, (thickness + 2, h + thickness + 2), face, scale, 255, thickness, cv2.LINE_AA)
    return canvas


def glyph_ttf(ch: str, font_path: str, height: int, stroke: int) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(font_path, int(height * 1.3))
    x0, y0, x1, y1 = font.getbbox(ch, stroke_width=stroke)
    img = Image.new("L", (x1 - x0 + 8, y1 - y0 + 8), 0)
    ImageDraw.Draw(img).text((4 - x0, 4 - y0), ch, fill=255, font=font, stroke_width=stroke, stroke_fill=255)
    return np.array(img)


def trim(mask: np.ndarray) -> np.ndarray:
    ys, xs = np.nonzero(mask > 20)
    return mask if not len(xs) else mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def jitter_glyph(g: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """글꼴 글자 하나: 크기·회전·기울임·폭 흔들기"""
    pad = max(g.shape)
    g = cv2.copyMakeBorder(g, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    m = cv2.getRotationMatrix2D((g.shape[1] / 2, g.shape[0] / 2), rng.uniform(-12, 12), rng.uniform(0.85, 1.15))
    m[0, 1] += rng.uniform(-0.35, 0.35)
    m[0, :2] *= rng.uniform(0.7, 1.3)
    return trim(cv2.warpAffine(g, m, (g.shape[1], g.shape[0])))


def render_line(text: str, style: dict, rng: np.random.Generator, height: int | None = None) -> tuple[np.ndarray, int, int]:
    """글자 줄 마스크(0~255), 글자 높이, 기준선 y. 캔버스 위아래로 글자 높이만큼 여유를 둠 (넘치는 획·옆 줄용)"""
    height = height or int(rng.integers(40, 72))
    thickness = int(rng.integers(2, 6))
    small_after_dot = rng.random() < 0.5
    placed = []  # (마스크, 글자 위에서의 세로 위치)
    after_dot = False
    gaps = []  # 글자 뒤 간격 — 점 앞뒤는 띄움 (겹치면 점이 묻혀 F5.5가 F55처럼 보임)
    for k, ch in enumerate(text):
        near_dot = ch == "." or (k + 1 < len(text) and text[k + 1] == ".")
        gaps.append(rng.uniform(0.04, 0.2) if near_dot else rng.uniform(-0.15, 0.25))
        h = int(height * (rng.uniform(0.6, 0.9) if after_dot and small_after_dot else 1.0))
        if ch == ".":
            r = max(2, int(thickness * rng.uniform(0.8, 1.5)))
            dot = np.zeros((2 * r + 2, 2 * r + 2), np.uint8)
            cv2.circle(dot, (r + 1, r + 1), r, 255, -1, cv2.LINE_AA)
            placed.append((dot, height - dot.shape[0]))
            after_dot = True
            continue
        if style["kind"] == "stroke":
            g, top = glyph_stroke(ch, h, thickness, rng)
            top += height - h
        elif style["kind"] == "ttf":
            g = jitter_glyph(trim(glyph_ttf(ch, style["font"], h, max(0, thickness - 2))), rng)
            top = height - g.shape[0]
        else:
            g = jitter_glyph(trim(glyph_hershey(ch, style["font"], h, thickness, style["italic"])), rng)
            top = height - g.shape[0]
        placed.append((g, top + int(rng.uniform(-0.1, 0.1) * height)))
    width = sum(g.shape[1] for g, _ in placed) + height * (len(placed) + 4)
    canvas = np.zeros((height * 4, width), np.uint8)
    x, cap_top = 2 * height, int(height * 1.5)
    for (g, top), gap in zip(placed, gaps):
        gh, gw = g.shape
        y = int(np.clip(cap_top + top, 0, canvas.shape[0] - gh))
        canvas[y:y + gh, x:x + gw] = np.maximum(canvas[y:y + gh, x:x + gw], g)
        x += gw + int(gap * height)  # 글자끼리 겹치기도 함
    return canvas[:, :x + 2 * height], height, cap_top + height


def add_strokes(mask: np.ndarray, text_mask: np.ndarray, height: int, thickness: int, rng: np.random.Generator) -> None:
    """글자에 붙는 화살표(왼쪽·오른쪽)·꼬리 선·용접선(세로선) — 정답 글자는 아님"""
    ys, xs = np.nonzero(text_mask > 20)
    x1, x2, y1, y2 = xs.min(), xs.max(), ys.min(), ys.max()
    mid = int((y1 + y2) / 2 + rng.uniform(-0.2, 0.2) * height)
    t = max(1, thickness)
    if rng.random() < 0.65:
        if rng.random() < 0.6:  # 왼쪽에서 글자 쪽으로 (→F…, 예시 2·3)
            tip, tail = x1 - int(rng.uniform(0, 0.15) * height), 0
        else:  # 오른쪽에서 글자 쪽으로 (…←, 예시 1)
            tip, tail = x2 + int(rng.uniform(0, 0.15) * height), mask.shape[1] - 1
        cv2.line(mask, (tail, mid + int(rng.uniform(-3, 3))), (tip, mid), 255, t, cv2.LINE_AA)
        d, head = (1 if tip > tail else -1), int(rng.uniform(0.2, 0.4) * height)
        if rng.random() < 0.3:  # 화살촉을 ⊃처럼 둥글게
            cv2.ellipse(mask, (tip - d * head // 2, mid), (head // 2, head // 2), 0, -90 * d + 90, 90 * d + 90, 255, t, cv2.LINE_AA)
        else:
            cv2.line(mask, (tip, mid), (tip - d * head, mid - head // 2), 255, t, cv2.LINE_AA)
            cv2.line(mask, (tip, mid), (tip - d * head, mid + head // 2), 255, t, cv2.LINE_AA)
    if rng.random() < 0.35:  # 글자 끝에서 길게 끌린 꼬리 (예시 2·3의 아랫줄)
        pts = np.array([[x2 - int(0.3 * height), y2 - int(0.2 * height)],
                        [min(mask.shape[1] - 1, x2 + int(rng.uniform(0.8, 2) * height)), y2 - int(rng.uniform(0, 0.5) * height)]])
        cv2.polylines(mask, [pts.astype(np.int32)], False, 255, t, cv2.LINE_AA)
    if rng.random() < 0.3:  # 용접선·판 끝 세로선
        x = int(rng.choice([max(0, x1 - int(0.5 * height)), min(mask.shape[1] - 1, x2 + int(0.5 * height))]))
        cv2.line(mask, (x, 0), (x + int(rng.uniform(-5, 5)), mask.shape[0] - 1), 255, t, cv2.LINE_AA)


def paste_neighbor(mask: np.ndarray, text_mask: np.ndarray, height: int, style: dict, rng: np.random.Generator) -> None:
    """위나 아래 줄(두세 줄로 쌓아 쓴 표기)이 잘린 글자 줄에 살짝 걸치게"""
    other, _, _ = render_line("V" if rng.random() < 0.3 else random_label(rng), style, rng,
                              height=int(height * rng.uniform(0.8, 1.2)))
    other = trim(other)
    ys, xs = np.nonzero(text_mask > 20)
    gap = int(rng.uniform(0.05, 0.35) * height)
    y = ys.min() - gap - other.shape[0] if rng.random() < 0.5 else ys.max() + gap
    x = int(xs.min() + rng.uniform(-0.3, 0.5) * height)
    y0, x0 = max(0, y), max(0, x)
    y1, x1 = min(mask.shape[0], y + other.shape[0]), min(mask.shape[1], x + other.shape[1])
    if y1 > y0 and x1 > x0:
        mask[y0:y1, x0:x1] = np.maximum(mask[y0:y1, x0:x1], other[y0 - y:y1 - y, x0 - x:x1 - x])


def elastic(layers: np.ndarray, rng: np.random.Generator, alpha: float, sigma: float) -> np.ndarray:
    """손 떨림 같은 부드러운 변형 (여러 겹을 같은 변형으로)"""
    h, w = layers.shape[:2]
    dx = cv2.GaussianBlur(rng.uniform(-1, 1, (h, w)).astype(np.float32), (0, 0), sigma) * alpha
    dy = cv2.GaussianBlur(rng.uniform(-1, 1, (h, w)).astype(np.float32), (0, 0), sigma) * alpha
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return cv2.remap(layers, gx + dx * sigma, gy + dy * sigma, cv2.INTER_LINEAR)


# ── 배경과 합성 ──

def background(shape: tuple[int, int], backgrounds: list[np.ndarray], rng: np.random.Generator) -> np.ndarray:
    h, w = shape
    if backgrounds and rng.random() < 0.5:
        src = backgrounds[int(rng.integers(len(backgrounds)))]
        s = max(h / src.shape[0], w / src.shape[1]) * rng.uniform(1.0, 3.0)
        src = cv2.resize(src, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        y, x = int(rng.integers(0, src.shape[0] - h + 1)), int(rng.integers(0, src.shape[1] - w + 1))
        return src[y:y + h, x:x + w].astype(np.float32)
    r = rng.random()
    if r < 0.45:  # 흰·밝은 철판 (예시 2)
        base = np.array([rng.uniform(165, 225)] * 3) + rng.uniform(-3, 3, 3)
    elif r < 0.92:  # 회색·어두운 철판 (예시 1·3)
        base = np.array([rng.uniform(60, 150)] * 3) + rng.uniform(-3, 3, 3)
    else:  # 녹 (BGR)
        base = np.array([rng.uniform(30, 60), rng.uniform(60, 95), rng.uniform(95, 140)])
    img = np.ones((h, w, 3), np.float32) * base
    low = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), max(h, w) / 6)
    img += (low / (np.abs(low).max() + 1e-6) * rng.uniform(5, 25))[..., None]  # 얼룩·조명 얼룩
    if rng.random() < 0.5:  # 연마 자국: 한 방향으로 긴 결
        streak = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), sigmaX=rng.uniform(8, 30), sigmaY=0.8)
        img += (streak / (np.abs(streak).max() + 1e-6) * rng.uniform(4, 12))[..., None]
    for _ in range(int(rng.integers(0, 4))):  # 가는 긁힘
        p1 = (int(rng.integers(0, w)), int(rng.integers(0, h)))
        p2 = (int(p1[0] + rng.uniform(-w, w) / 2), int(p1[1] + rng.uniform(-h, h) / 2))
        cv2.line(img, p1, p2, (base + rng.uniform(-30, 30)).tolist(), 1, cv2.LINE_AA)
    img += rng.normal(0, rng.uniform(2, 8), (h, w, 1))
    return img


def ink_on(bg: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """글씨 색 (대부분 흰 분필·석필). 배경과 밝기 차이가 MIN_GAP보다 작으면 벌림 → (글씨 색, 배경)"""
    r = rng.random()
    ink = (np.array([rng.uniform(200, 255)] * 3) if r < 0.8
           else np.array([40.0, 210.0, 230.0]) if r < 0.88  # 노란 페인트 마커 (BGR)
           else np.array([rng.uniform(10, 50)] * 3))  # 검은 마커
    gap = float(ink.mean() - bg.mean())
    if abs(gap) < MIN_GAP:
        if gap >= 0:  # 밝은 글씨: 글씨를 올리고, 255를 넘으면 배경을 내림
            need = bg.mean() + MIN_GAP
            if need > 255:
                bg = bg - (need - 255)
                need = 255
            ink = np.maximum(ink, need)
        else:
            need = bg.mean() - MIN_GAP
            if need < 0:
                bg = bg - need
                need = 0
            ink = np.minimum(ink, need)
    return ink, bg


def paint(bg: np.ndarray, mask: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """분필 질감(획이 군데군데 끊기고 흐림)으로 마스크를 배경 위에 칠함"""
    grain = cv2.GaussianBlur(rng.uniform(0, 1, mask.shape).astype(np.float32), (0, 0), rng.uniform(0.6, 1.5))
    alpha = (mask / 255.0) * np.clip(grain * rng.uniform(1.4, 2.4), 0, 1) * rng.uniform(0.75, 1.0)
    alpha = cv2.GaussianBlur(alpha, (0, 0), rng.uniform(0.3, 1.2))
    ink, bg = ink_on(bg, rng)
    img = bg * (1 - alpha[..., None]) + ink * alpha[..., None]
    h, w = mask.shape
    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    light = 1 + rng.uniform(-0.2, 0.2) * (gx / w - 0.5) + rng.uniform(-0.2, 0.2) * (gy / h - 0.5)  # 조명 기울기
    return np.clip(img * light[..., None], 0, 255).astype(np.uint8)


def degrade(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """흔들림·JPEG 압축"""
    if rng.random() < 0.2:
        k = int(rng.integers(2, 4))
        img = cv2.filter2D(img, -1, np.ones((1, k), np.float32) / k)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(rng.integers(35, 95))])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def compose_line(text: str, style: dict, backgrounds: list[np.ndarray], rng: np.random.Generator) -> np.ndarray:
    """글자 줄 이미지 하나 (인식기 학습용)"""
    text_mask, height, _ = render_line(text, style, rng)
    mask = text_mask.copy()
    add_strokes(mask, text_mask, height, int(rng.integers(2, 5)), rng)
    if rng.random() < 0.4:
        paste_neighbor(mask, text_mask, height, style, rng)
    layers = elastic(np.dstack([mask, text_mask]), rng, alpha=rng.uniform(0.8, 3.0), sigma=rng.uniform(6, 14))
    h, w = layers.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = src + rng.uniform(-0.06, 0.06, (4, 2)).astype(np.float32) * np.float32([w, h])
    layers = cv2.warpPerspective(layers, cv2.getPerspectiveTransform(src, dst), (w, h))
    img = paint(background((h, w), backgrounds, rng), layers[..., 0], rng)
    ys, xs = np.nonzero(layers[..., 1] > 30)  # 자르는 기준은 정답 글자만 (화살표·옆 줄은 여백에 걸침)
    m = int(height * rng.uniform(0.15, 0.5))
    img = img[max(0, ys.min() - m):ys.max() + m, max(0, xs.min() - m):xs.max() + m]
    s = rng.uniform(16, 64) / img.shape[0]  # 운영측 예시의 글자 줄은 20~70px
    img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return degrade(img, rng)


def order_points(pts: np.ndarray) -> list[list[int]]:
    """4점을 왼쪽 위부터 시계 방향으로"""
    c = pts.mean(0)
    pts = pts[np.argsort(np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0]))]
    start = int(np.argmin(pts.sum(1)))
    return np.roll(pts, -start, axis=0).round().astype(int).tolist()


def compose_scene(styles: list[dict], stroke_ratio: float, backgrounds: list[np.ndarray],
                  rng: np.random.Generator) -> tuple[np.ndarray, list[dict]]:
    """철판 한 장에 표기 묶음 1~3개(묶음마다 1~3줄 + 화살표) + 정답이 아닌 낙서·기준 표시 (검출기 학습용)"""
    W = int(rng.uniform(640, 1280))
    H = int(W * rng.uniform(0.6, 1.0))
    alpha = np.zeros((H, W), np.uint8)
    boxes = []
    groups = int(rng.integers(1, 4))
    cell_w = W // groups
    for g in range(groups):
        style = pick_style(styles, stroke_ratio, rng)
        size = int(rng.uniform(18, 60))  # 글자 높이 (px)
        n_lines = int(rng.choice([1, 2, 3], p=[0.4, 0.4, 0.2]))
        labels = [random_label(rng)] + ["V" if rng.random() < 0.4 else random_label(rng) for _ in range(n_lines - 1)]
        ox = int(g * cell_w + rng.uniform(0.05, 0.3) * cell_w)
        oy = int(rng.uniform(0.1, 0.6) * H)
        angle = rng.uniform(-12, 12)
        for i, label in enumerate(labels):
            text_mask, height, _ = render_line(label, style, rng, height=size)
            mask = text_mask.copy()
            if i == 0:
                add_strokes(mask, text_mask, height, max(1, size // 15), rng)
            layers = trim_pair(elastic(np.dstack([mask, text_mask]), rng, alpha=rng.uniform(0.8, 2.5), sigma=rng.uniform(6, 12)))
            ty, tx = [v.min() for v in np.nonzero(layers[..., 1] > 30)]  # 줄마다 글자 왼쪽 위를 묶음 기준점에 맞춤
            m = cv2.getRotationMatrix2D((0, 0), angle, 1.0)
            m[:, 2] = -m[:, :2] @ [tx, ty] + [ox + rng.uniform(-0.2, 0.2) * size, oy + i * size * rng.uniform(1.2, 1.6)]
            placed = cv2.warpAffine(layers, m, (W, H))
            alpha = np.maximum(alpha, placed[..., 0])
            ys, xs = np.nonzero(placed[..., 1] > 30)
            if len(xs) < 10 or xs.min() <= 0 or ys.min() <= 0 or xs.max() >= W - 1 or ys.max() >= H - 1:
                continue  # 사진 밖으로 잘린 줄은 정답에서 뺌 (글자는 그대로 둬도 학습에 큰 해 없음)
            rect = cv2.boxPoints(cv2.minAreaRect(np.column_stack([xs, ys]).astype(np.float32)))
            boxes.append({"transcription": label, "points": order_points(rect)})
    for _ in range(int(rng.integers(0, 4))):  # 정답이 아닌 분필 표시: 기준 십자·긴 선
        x, y, r = int(rng.uniform(0, W)), int(rng.uniform(0, H)), int(rng.uniform(10, 40))
        if rng.random() < 0.5:
            cv2.line(alpha, (x - r, y), (x + r, y), 255, 2, cv2.LINE_AA)
            cv2.line(alpha, (x, y - r), (x, y + r), 255, 2, cv2.LINE_AA)
        else:
            cv2.line(alpha, (x, y), (int(x + rng.uniform(-4, 4) * r), int(y + rng.uniform(-4, 4) * r)), 255, 2, cv2.LINE_AA)
    img = paint(background((H, W), backgrounds, rng), alpha, rng)
    if rng.random() < 0.6:  # 작은 사진처럼 뭉개기 (운영측 예시는 긴 변 178~343px)
        s = rng.uniform(0.25, 0.6)
        img = cv2.resize(cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), (W, H), interpolation=cv2.INTER_CUBIC)
    return degrade(img, rng), boxes


def trim_pair(layers: np.ndarray) -> np.ndarray:
    ys, xs = np.nonzero(layers[..., 0] > 20)
    return layers[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def styles_for(split: str, fonts: list[str]) -> list[dict]:
    """split별 글꼴 글씨체 (stroke는 따로). TTF는 정렬 순서로 번갈아 train/eval에 나눔"""
    names = ["train", "eval"] if split == "all" else [split]
    styles = [{"kind": "hershey", "font": f, "italic": it} for n in names for f in HERSHEY[n] for it in (False, True)]
    for i, f in enumerate(sorted(fonts)):
        if split == "all" or (i % 2 == 0) == (split == "train"):
            styles.append({"kind": "ttf", "font": f})
    return styles


def pick_style(styles: list[dict], stroke_ratio: float, rng: np.random.Generator) -> dict:
    return {"kind": "stroke"} if rng.random() < stroke_ratio else styles[int(rng.integers(len(styles)))]


def load_backgrounds(pattern: str | None, limit: int = 60) -> list[np.ndarray]:
    if not pattern:
        return []
    out = []
    for p in sorted(glob.glob(pattern, recursive=True))[:limit]:
        img = cv2.imread(p)
        if img is not None:
            s = 800 / max(img.shape[:2])
            out.append(cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else img)
    return out


_SHARED: dict = {}  # 작업 프로세스가 같이 쓰는 설정 (styles 등)


def _init(shared: dict) -> None:
    _SHARED.update(shared)


def _make(i: int) -> str:
    """샘플 하나 만들어 저장하고 라벨 줄을 돌려줌. 샘플마다 난수를 (seed, i)로 고정 — 작업 프로세스 수와 상관없이 같은 결과"""
    a = _SHARED
    rng = np.random.default_rng([a["seed"], i])
    name = f"images/{i:05d}.jpg"
    if a["mode"] == "lines":
        text = random_label(rng)
        img = compose_line(text, pick_style(a["styles"], a["stroke_ratio"], rng), a["backgrounds"], rng)
        line = f"{name}\t{text}"
    else:
        img, boxes = compose_scene(a["styles"], a["stroke_ratio"], a["backgrounds"], rng)
        line = f"{name}\t{json.dumps(boxes, ensure_ascii=False)}"
    cv2.imwrite(str(a["out"] / name), img, [cv2.IMWRITE_JPEG_QUALITY, 95 if a["mode"] == "lines" else 85])
    return line


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=["lines", "scenes"], default="lines")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--styles", choices=["train", "eval", "all"], default="train")
    parser.add_argument("--stroke-ratio", type=float, default=0.6, help="운영측 버릇 글씨체(stroke) 비율")
    parser.add_argument("--fonts", action="append", default=[], help="TTF 글꼴 glob, 여러 번 가능 (예: '/usr/share/fonts/**/Humor*')")
    parser.add_argument("--backgrounds", help="배경 사진 glob — 글자가 없는 사진만")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=1, help="동시에 만드는 프로세스 수 (CPU 수만큼)")
    args = parser.parse_args()

    fonts = sorted({f for pattern in args.fonts for f in glob.glob(pattern, recursive=True)  # 폴더 이름이 걸려도 글꼴 파일만
                    if Path(f).is_file() and Path(f).suffix.lower() in {".ttf", ".ttc", ".otf"}})
    styles = styles_for(args.styles, fonts)
    backgrounds = load_backgrounds(args.backgrounds)
    (args.out / "images").mkdir(parents=True, exist_ok=True)
    shared = {"mode": args.mode, "seed": args.seed, "styles": styles, "stroke_ratio": args.stroke_ratio,
              "backgrounds": backgrounds, "out": args.out}
    if args.workers > 1:
        import multiprocessing as mp

        with mp.get_context("fork").Pool(args.workers, initializer=_init, initargs=(shared,)) as pool:
            lines = list(pool.imap(_make, range(args.n), chunksize=32))
    else:
        _init(shared)
        lines = [_make(i) for i in range(args.n)]
    label_file = "labels.tsv" if args.mode == "lines" else "det_labels.txt"
    (args.out / label_file).write_text("\n".join(lines) + "\n", encoding="utf-8")
    (args.out / "manifest.json").write_text(json.dumps({
        "mode": args.mode, "n": args.n, "styles": args.styles, "stroke_ratio": args.stroke_ratio, "seed": args.seed,
        "fonts": [Path(f).name for f in fonts], "backgrounds": len(backgrounds),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{args.mode} {args.n}장 → {args.out} (stroke {args.stroke_ratio:.0%} + 글꼴 {len(styles)}개: TTF "
          f"{[Path(f).name for f in fonts]}, 배경 사진 {len(backgrounds)}장)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
