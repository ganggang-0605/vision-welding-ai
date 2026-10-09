"""b. 문자/기호 DB: 워크스페이스 사전 대조"""
import re
from difflib import SequenceMatcher

from db_context_interpreter.ocr_text import ocr_variants
from db_context_interpreter.readings import normalize
from db_context_interpreter.welding import read_thickness

FUZZY_MIN = 0.8          # 유사 일치로 볼 최소 유사도 (difflib ratio)
FIXED_PENALTY = 0.9     # 헷갈리는 글자를 고쳐서 맞힌 읽기의 점수 배수
AMBIGUOUS_MARGIN = 0.2   # 1단계 후보 확률이 이만큼 이내로 붙어 있고 사전 해석이 달라지면 ambiguous_reading
CODE_VALUE = re.compile(r"^([A-Z]+)([0-9]+(?:\.[0-9]+)?)$")  # 코드 + 숫자 (수기 각장 F5.5, V6, S4.5)
# 치수(블록 사진의 350, 835 등) — 용접 표기가 아니라 '해석 못 함' 경고를 붙이지 않음
DIMENSION = re.compile(r"^[0-9]{2,5}(?:\.[0-9]+)?$")
# 선체 필렛 각장으로 볼 수 있는 크기 (기준표 각장 3~13mm, data/seed/SOURCES.md). 밖이면 오인식으로 봄
LEG_MIN_MM, LEG_MAX_MM = 2.0, 25.0


def is_dimension(value: str) -> bool:
    return bool(DIMENSION.match(normalize(value)))


def is_leg_entry(entry: dict) -> bool:
    """수기 각장 코드인지 (데모 사전 F · V · S — 뜻에 '각장'이 있는 글자 항목)"""
    return entry["kind"] == "text" and "각장" in entry["meaning"]


def plausible_leg(digits: str) -> tuple[float, str] | None:
    """(각장 mm, 숫자 표기). 범위 밖이면 소수점이 빠진 두 자리(55 → 5.5)로 보고 고침. 고쳐도 밖이면 None"""
    size = float(digits)
    if LEG_MIN_MM <= size <= LEG_MAX_MM:
        return size, digits
    if "." not in digits and len(digits) == 2 and LEG_MIN_MM <= float(fixed := f"{digits[0]}.{digits[1]}") <= LEG_MAX_MM:
        return float(fixed), fixed
    return None


class Dictionary:
    """context_input["symbols"] 색인 (code · aliases, 대소문자·공백·대시 무시)"""

    def __init__(self, entries: list[dict]) -> None:
        self.entries = entries
        self.codes = {normalize(e["code"]): e for e in entries}
        self.aliases = {normalize(a): e for e in entries for a in e["aliases"]}
        self.by_code = {e["code"]: e for e in entries}

    def lookup(self, value: str) -> tuple[dict, str] | None:
        """(사전 항목, "exact" | "alias")"""
        key = normalize(value)
        if key in self.codes:
            return self.codes[key], "exact"
        if key in self.aliases:
            return self.aliases[key], "alias"
        return None

    def code_with_value(self, value: str) -> tuple[dict, str] | None:
        """코드 뒤에 숫자가 붙은 표기 (예: F5.5 → F 항목, "3F 용접장 각장 5.5mm").
        각장 코드인데 크기가 말이 안 되면(F55) 소수점이 빠진 것으로 보고 고친 값의 뜻 (leg_fix), 고칠 수 없으면 None"""
        m = CODE_VALUE.match(normalize(value))
        entry = self.codes.get(m.group(1)) if m else None
        if not entry or entry["kind"] != "text":
            return None
        digits = m.group(2)
        if is_leg_entry(entry):
            leg = plausible_leg(digits)
            if leg is None:
                return None
            digits = leg[1]
        base, _, note = entry["meaning"].partition("(")
        unit = "mm" if "mm" in note else ""
        return entry, f"{base.strip()} {digits}{unit}"

    def leg_fix(self, value: str) -> str | None:
        """소수점이 빠진 각장 표기를 고친 값 (F55 → F5.5). 고칠 게 없으면 None"""
        m = CODE_VALUE.match(normalize(value))
        entry = self.codes.get(m.group(1)) if m else None
        if not entry or not is_leg_entry(entry) or (leg := plausible_leg(m.group(2))) is None or leg[1] == m.group(2):
            return None
        return m.group(1) + leg[1]

    def implausible_leg(self, value: str) -> float | None:
        """각장 코드 + 고쳐도 말이 안 되는 크기(F120)면 그 크기"""
        m = CODE_VALUE.match(normalize(value))
        entry = self.codes.get(m.group(1)) if m else None
        if entry and is_leg_entry(entry) and plausible_leg(m.group(2)) is None:
            return float(m.group(2))
        return None

    def reading_key(self, value: str) -> tuple[str, float | None] | None:
        """사전 해석이 같은지 비교하는 키 (코드, 숫자 값). V6 · V6.0은 같고 V6.0 · V6.5는 다름. 사전에 없으면 None"""
        if found := self.lookup(value):
            return found[0]["code"], None
        if self.code_with_value(value):
            m = CODE_VALUE.match(normalize(self.leg_fix(value) or value))
            return m.group(1), float(m.group(2))
        return None

    def fuzzy(self, value: str) -> tuple[dict, float] | None:
        key = normalize(value)
        best = None
        for k, entry in [*self.codes.items(), *self.aliases.items()]:
            if len(k) < 2 or len(key) < 2:  # 한 글자 코드는 유사 일치로 보지 않음 (F ↔ E 같은 오인식이 너무 쉬움)
                continue
            ratio = SequenceMatcher(None, key, k).ratio()
            if ratio >= FUZZY_MIN and (best is None or ratio > best[1]):
                best = (entry, ratio)
        return best


def match_dictionary(
    readings: list[dict], context_input: dict, vlm_meanings: dict[str, str], vlm_prob: float, skip: set[str],
) -> list[tuple[dict, dict]]:
    """1단계 글자·기호(작업자가 고친 값 우선)를 context_input["symbols"]의 code·aliases와 대조 → [(읽기, DictionaryMatch)].
    읽기는 줄을 나눈 표기 단위(ocr_text.segment). skip: 부재 번호로 쓴 읽기의 key (조립 경로 DB에서 해석)

    match: exact 그대로 일치 / alias 별칭 일치 / candidate 1단계 후보 중 하나가 일치 / fuzzy 유사 일치 /
           vlm 사전에 없지만 VLM이 해석 / none 해석 못 함
    """
    dictionary = Dictionary(context_input["symbols"])
    matches = []
    for r in readings:
        if r["key"] in skip:
            continue
        whole = r["value"] == r["line"]  # VLM 의미 · 작업자 의미는 1단계 ID(줄 전체) 단위
        m = match_one(r, dictionary, vlm_meanings.get(r["ref_id"]) if whole else None, vlm_prob)
        if r["meaning"] and whole:  # 작업자가 직접 정한 의미가 사전보다 우선
            m["meaning"] = r["meaning"]
        matches.append((r, m))
    return matches


def match_one(r: dict, dictionary: Dictionary, vlm_meaning: str | None, vlm_prob: float) -> dict:
    ref, value, prob = [r["ref_id"]], r["value"], r["prob"]

    def result(raw: str, entry: dict | None, match: str, score: float, meaning: str | None = None) -> dict:
        return {
            "ref_ids": ref, "raw": raw, "code": entry["code"] if entry else None,
            "meaning": meaning or (entry["meaning"] if entry else None), "match": match, "score": round(score, 2),
        }

    if value != "unknown":
        if found := dictionary.lookup(value):
            return result(value, found[0], found[1], prob)
        if found := dictionary.code_with_value(value):
            if fixed := dictionary.leg_fix(value):  # F55 → F5.5 (소수점이 빠짐)
                return result(fixed, found[0], "fuzzy", prob * FIXED_PENALTY, found[1])
            return result(value, found[0], "exact", prob, found[1])
    for candidate, candidate_prob in r["candidates"]:
        if found := dictionary.lookup(candidate) or dictionary.code_with_value(candidate):
            entry, extra = found
            return result(candidate, entry, "candidate", candidate_prob, None if extra in ("exact", "alias") else extra)
    if value != "unknown":
        for fixed in ocr_variants(value):  # OCR이 헷갈린 글자를 고쳐 다시 대조 (F5,5 → F5.5, 54.5 → S4.5)
            if dictionary.leg_fix(fixed):  # 글자도 고치고 소수점도 넣어야 맞는 읽기(550 → S50 → S5.0)는 지나친 보정
                continue
            if found := dictionary.lookup(fixed) or dictionary.code_with_value(fixed):
                entry, extra = found
                return result(fixed, entry, "fuzzy", prob * FIXED_PENALTY, None if extra in ("exact", "alias") else extra)
        if is_dimension(value):
            return result(value, None, "none", prob, f"치수 {normalize(value)}mm (용접 표기 아님)")
        if found := dictionary.fuzzy(value):
            return result(value, found[0], "fuzzy", prob * found[1])
    if vlm_meaning:
        return result(value, None, "vlm", vlm_prob, vlm_meaning)
    thickness, read_as = read_thickness(value)
    if thickness is None:
        return result(value, None, "none", 0.0)
    fixed = read_as != normalize(value)
    return result(read_as if fixed else value, None, "none", prob * (FIXED_PENALTY if fixed else 1), f"판 두께 {thickness:g}mm")


def dictionary_conflicts(pairs: list[tuple[dict, dict]], context_input: dict) -> list[dict]:
    """dictionary_unmatched(사전에 없음: fuzzy · vlm · none) · ambiguous_reading(후보마다 사전 해석이 달라짐 — 각장은 숫자까지).
    작업자가 고치거나 확인한 표기는 넣지 않음"""
    dictionary = Dictionary(context_input["symbols"])
    conflicts = []
    for r, m in pairs:
        ref = m["ref_ids"][0]
        if r["corrected"]:
            continue
        raw = m["raw"]
        read = f"'{r['value']}' 표기를 '{raw}'로 보정해" if normalize(raw) != normalize(r["value"]) else f"'{raw}' 표기는"
        if m["match"] == "none" and is_dimension(raw):
            pass  # 치수는 용접 표기가 아님
        elif m["match"] == "fuzzy" and dictionary.leg_fix(r["value"]):
            conflicts.append({
                "type": "ambiguous_reading", "severity": "warning",
                "message": f"각장 '{r['value']}'는 너무 커서 소수점이 빠진 것으로 보고 '{raw}'({m['meaning']})로 봄",
                "ref_ids": [ref],
            })
        elif m["match"] == "none" and (size := dictionary.implausible_leg(r["value"])) is not None:
            conflicts.append(unmatched(f"각장 '{r['value']}'({size:g}mm)는 현실적인 크기가 아니라 해석하지 않음", "warning", ref))
        elif m["match"] == "fuzzy" and normalize(raw) != normalize(r["value"]):
            conflicts.append(unmatched(f"{read} '{m['code']}'({m['meaning']})로 봄 — OCR이 비슷한 글자를 헷갈렸을 수 있음", "info", ref))
        elif m["match"] == "fuzzy":
            conflicts.append(unmatched(f"{read} 사전에 그대로 없어 비슷한 '{m['code']}'({m['meaning']})로 봄", "info", ref))
        elif m["match"] == "vlm":
            conflicts.append(unmatched(f"{read} 문자/기호 사전에 없어 VLM 해석({m['meaning']})을 사용함", "info", ref))
        elif m["match"] == "none" and m["meaning"]:
            conflicts.append(unmatched(f"{read} 문자/기호 사전에 없어 표기 규칙으로 해석함({m['meaning']})", "info", ref))
        elif m["match"] == "none" and ref[0] == "v" and r["kind"] == "symbol":
            # VLM이 본 이름 모를 기호(획 끝 갈고리 등) — 1단계가 검출한 기호가 아니라 확인 항목으로 올리지 않음
            conflicts.append(unmatched(f"VLM이 본 기호 '{raw}'를 문자/기호 사전에서 찾지 못함", "info", ref))
        elif m["match"] == "none":
            conflicts.append(unmatched(f"{read} 문자/기호 사전에 없고 해석하지 못함", "warning", ref))

        chosen = dictionary.reading_key(m["raw"])
        rivals = [
            (value, p) for value, p in r["candidates"]
            if p >= r["prob"] - AMBIGUOUS_MARGIN
            and (key := dictionary.reading_key(value)) is not None and key != chosen
        ]
        if rivals:
            others = ", ".join(f"'{v}'({p:.0%})" for v, p in rivals)
            conflicts.append({
                "type": "ambiguous_reading", "severity": "warning",
                "message": f"'{r['value']}'({r['prob']:.0%})와 {others} 중 어느 것인지에 따라 해석이 달라짐",
                "ref_ids": [ref],
            })
    return conflicts


def unmatched(message: str, severity: str, ref: str) -> dict:
    return {"type": "dictionary_unmatched", "severity": severity, "message": message, "ref_ids": [ref]}
