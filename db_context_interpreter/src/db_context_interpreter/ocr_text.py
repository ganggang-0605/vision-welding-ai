"""실제 OCR 출력 다루기 — PaddleOCR은 표기 여러 개를 한 줄로 읽고(P-1 FW t=10), 비슷한 글자를 자주 헷갈림(1→I, 0→O, 5→S)
(vision/reports/phase1_baseline.md). 대조 전에 줄을 표기 단위로 나누고, 대조가 안 되면 헷갈리는 글자를 고쳐 다시 대조함"""
import re
from collections.abc import Callable

from db_context_interpreter.readings import normalize

# 숫자 자리에 나온 글자 → 숫자 (OCR이 자주 헷갈리는 쌍)
DIGIT_FOR = {"O": "0", "D": "0", "Q": "0", "I": "1", "L": "1", "|": "1", "!": "1", "Z": "2", "S": "5", "G": "6", "B": "8"}
# 맨 앞(코드 자리)에 나온 숫자 → 글자 (예: S4.5를 54.5로 읽음)
LETTER_FOR = {"5": "S", "0": "O", "1": "I", "8": "B", "2": "Z"}
PREFIX = re.compile(r"^([A-Z]+)([-=:]?)(.*)$")  # 코드 글자 + 구분 기호 + 숫자 자리 (P-1, T=10, F5.5)
MAX_SPAN = 3  # 붙여 볼 최대 토큰 수 (t = 10)


def digitize(value: str) -> str:
    return "".join(DIGIT_FOR.get(c, c) for c in value).replace(",", ".")


def ocr_variants(value: str) -> list[str]:
    """헷갈리는 글자를 고친 읽기 후보 (원래 읽기는 빼고, 그럴듯한 순서). 원래 읽기로 대조가 안 될 때만 씀"""
    key = normalize(value)
    variants = []
    if m := PREFIX.match(key):
        letters, sep, tail = m.groups()
        # 코드가 몇 글자인지 모르므로 긴 쪽부터: 나머지 글자는 숫자 자리로 봄 (P-I → P-1, TI2 → T12, F5,5 → F5.5)
        variants += [letters[:k] + digitize(letters[k:]) + sep + digitize(tail) for k in range(len(letters), 0, -1)]
    variants.append(key.replace(",", "."))
    if len(key) >= 2 and key[0] in LETTER_FOR:
        variants.append(LETTER_FOR[key[0]] + digitize(key[1:]))  # 54.5 → S4.5
    return [v for v in dict.fromkeys(variants) if v != key]


def segment(readings: list[dict], known: Callable[[str], bool]) -> list[dict]:
    """글자 줄을 표기 단위로 나눔 → 읽기마다 key(ref_id#순번) · line(1단계가 읽은 줄 전체)을 붙임.

    줄 전체가 아는 표기(사전 · 조립 트리 · 판 두께)면 그대로 두고, 아니면 공백으로 나눈 뒤 붙여야 아는 표기가 되는
    이웃 토큰(t = 10, V 6.0)은 다시 붙임. 나눈 토큰은 모두 같은 1단계 ID를 근거로 가리킴.
    1단계 후보(candidates)는 줄 전체에 대한 것이라 한 토큰짜리 줄에만 남김"""
    out = []
    for r in readings:
        tokens = r["value"].split() if r["kind"] == "text" else [r["value"]]
        if len(tokens) <= 1 or known(r["value"]):
            out.append({**r, "key": f"{r['ref_id']}#0", "line": r["value"]})
            continue
        pieces, i = [], 0
        while i < len(tokens):
            j = next(j for j in range(min(len(tokens), i + MAX_SPAN), i, -1) if j == i + 1 or known(" ".join(tokens[i:j])))
            pieces.append(" ".join(tokens[i:j]))
            i = j
        out += [{**r, "value": piece, "candidates": [], "key": f"{r['ref_id']}#{n}", "line": r["value"]}
                for n, piece in enumerate(pieces)]
    return out
