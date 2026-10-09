"""평가용 촬영 조건 흉내: 정답이 있는 사진에 저조도·빛 반사·오염(녹)·기울어짐을 인위적으로 입힘 (eval_pipeline.py --simulate)

조건별로 따로 찍은 정답 사진이 없을 때 같은 사진으로 조건별 차이를 보려는 것 — 실제 현장 사진과 다를 수 있으니
결과를 쓸 때는 "조건은 합성"이라고 밝힘. 이름은 data/annotations/README.md 의 conditions 값과 같음.
사진마다·조건마다 난수를 고정해 다시 돌려도 같은 이미지가 나옴.
"""
import zlib

import cv2
import numpy as np

LABELS = {"dark": "저조도", "glare": "빛 반사", "stain": "표면 오염·녹", "skewed": "기울어짐"}


def _rng(name: str, condition: str) -> np.random.Generator:
    return np.random.default_rng(zlib.crc32(f"{name}|{condition}".encode()))


def _blob(shape: tuple[int, int], rng: np.random.Generator, sigma: float) -> np.ndarray:
    """0~1 부드러운 얼룩 (저주파 잡음)"""
    noise = cv2.GaussianBlur(rng.normal(0, 1, shape).astype(np.float32), (0, 0), sigma)
    return (noise - noise.min()) / (np.ptp(noise) + 1e-6)


def dark(img: np.ndarray, rng: np.random.Generator, boxes: list) -> np.ndarray:
    """어두운 곳: 감마로 어둡게 + 밝기를 낮춤 + 센서 잡음"""
    x = (img.astype(np.float32) / 255) ** rng.uniform(1.6, 2.2) * rng.uniform(0.4, 0.55) * 255
    x += rng.normal(0, rng.uniform(4, 8), img.shape)
    return np.clip(x, 0, 255).astype(np.uint8)


def glare(img: np.ndarray, rng: np.random.Generator, boxes: list) -> np.ndarray:
    """빛 반사: 표기 하나에 걸치는 흰 반사광 (가운데는 거의 하얗게 날아감)"""
    h, w = img.shape[:2]
    x1, y1, x2, y2 = boxes[int(rng.integers(len(boxes)))] if boxes else (0, 0, w, h)
    cx, cy = rng.uniform(x1, x2), rng.uniform(y1, y2)
    r = rng.uniform(1.0, 1.6) * max(x2 - x1, y2 - y1, min(h, w) * 0.15)
    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    ratio = rng.uniform(1.5, 3.0)  # 길쭉한 반사
    d = ((gx - cx) / r) ** 2 + ((gy - cy) / (r / ratio)) ** 2
    mask = np.exp(-d * 2.0)[..., None] * rng.uniform(0.75, 0.95)
    return np.clip(img * (1 - mask) + 255 * mask, 0, 255).astype(np.uint8)


def stain(img: np.ndarray, rng: np.random.Generator, boxes: list) -> np.ndarray:
    """표면 오염·녹: 갈색 녹 얼룩 + 작은 검은 점"""
    h, w = img.shape[:2]
    blob = _blob((h, w), rng, max(h, w) / 12)
    mask = np.clip((blob - rng.uniform(0.45, 0.6)) * 4, 0, 1) * rng.uniform(0.45, 0.7)
    texture = 0.75 + 0.5 * _blob((h, w), rng, 2.0)
    rust = np.array([30, 60, 115], np.float32) * texture[..., None]  # BGR 갈색
    out = img * (1 - mask[..., None]) + rust * mask[..., None]
    for _ in range(int(rng.integers(20, 50))):  # 점 크기는 사진 크기에 맞춤 (작은 사진에 큰 점이 찍히지 않게)
        cv2.circle(out, (int(rng.uniform(0, w)), int(rng.uniform(0, h))),
                   max(1, int(min(h, w) * rng.uniform(0.002, 0.006))), (25, 25, 30), -1, cv2.LINE_AA)
    return np.clip(out, 0, 255).astype(np.uint8)


def skewed(img: np.ndarray, rng: np.random.Generator, boxes: list) -> np.ndarray:
    """비스듬히 찍음: 한쪽 변을 줄인 원근 + 회전"""
    h, w = img.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    k = rng.uniform(0.15, 0.25)
    dst = src.copy()
    # 멀어지는 변 하나를 줄임: (꼭짓점, 축, 방향) — 왼쪽 · 오른쪽 · 위 · 아래
    sides = [[(0, 1, 1), (3, 1, -1)], [(1, 1, 1), (2, 1, -1)], [(0, 0, 1), (1, 0, -1)], [(3, 0, 1), (2, 0, -1)]]
    for corner, axis, sign in sides[int(rng.integers(4))]:
        dst[corner, axis] += sign * k * (h if axis == 1 else w)
    m = cv2.getRotationMatrix2D((w / 2, h / 2), rng.uniform(8, 15) * rng.choice([-1, 1]), 1.0)
    rot = np.vstack([m, [0, 0, 1]]) @ cv2.getPerspectiveTransform(src, dst)
    fill = tuple(float(v) for v in img.reshape(-1, img.shape[2]).mean(0))  # 사진 밖은 평균 색 (늘인 줄무늬 대신)
    return cv2.warpPerspective(img, rot, (w, h), borderMode=cv2.BORDER_CONSTANT, borderValue=fill)


TRANSFORMS = {"dark": dark, "glare": glare, "stain": stain, "skewed": skewed}


def simulate(img: np.ndarray, condition: str, name: str, boxes: list | None = None) -> np.ndarray:
    """condition(dark · glare · stain · skewed)을 입힌 사진. name = 사진 이름 (난수 고정용), boxes = 정답 글자 상자 (반사 위치)"""
    return TRANSFORMS[condition](img, _rng(name, condition), boxes or [])
