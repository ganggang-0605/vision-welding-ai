"""수기 각장 표기 형식: F(3F 용접장) · V(2F 용접장) · S(스티프너) + 각장(mm), 예: F5.5 · V5 · S6.5 (README 셀 형태와 각장)

인식기가 낸 글자를 이 형식에 맞춰 바로잡음 — 첫 글자는 F·V·S, 나머지는 숫자와 소수점만 올 수 있으니
헷갈리는 글자를 자리에 맞게 바꿈 (예: 첫 자리 5 → S, 숫자 자리 O → 0, 손글씨 V를 U로 읽은 것 → V)
"""
import re

LETTERS = "FVS"
CHARSET = LETTERS + "0123456789."
PATTERN = re.compile(r"[FVS]\d{1,2}(?:\.\d)?")

# 첫 자리(용접 종류)에서 F·V·S로 볼 수 있는 글자
_AS_LETTER = {"f": "F", "F": "F", "E": "F", "P": "F", "T": "F",
              "v": "V", "V": "V", "u": "V", "U": "V", "Y": "V", "y": "V",
              "s": "S", "S": "S", "5": "S", "$": "S", "§": "S"}
# 숫자 자리에서 숫자로 볼 수 있는 글자
_AS_DIGIT = {"O": "0", "o": "0", "D": "0", "Q": "0", "I": "1", "l": "1", "|": "1", "i": "1", "!": "1",
             "Z": "2", "z": "2", "B": "8", "b": "6", "G": "6", "S": "5", "s": "5", "$": "5", "q": "9", "g": "9",
             "A": "4", "T": "7", "/": "7", ",": ".", "·": "."}


def to_marking(text: str) -> str | None:
    """인식 결과 → 각장 표기 (형식에 맞출 수 없으면 None). 앞뒤 잡글자(화살표를 글자로 읽은 것 등)는 버림.
    숫자 없이 글자만 쓴 줄(운영측 예시 1·3의 V)은 읽은 결과가 그 글자 하나뿐일 때만 인정"""
    s = "".join(ch for ch in text if not ch.isspace())
    if len(s) == 1 and s in _AS_LETTER and not s.isdigit():
        return _AS_LETTER[s]
    for start, ch in enumerate(s):
        letter = _AS_LETTER.get(ch)
        if letter is None:
            continue
        rest = []
        for c in s[start + 1:]:
            d = c if c.isdigit() or c == "." else _AS_DIGIT.get(c)
            if d is None:
                break
            rest.append(d)
        found = PATTERN.match(letter + "".join(rest))
        if found:
            return found.group(0)
    return None
