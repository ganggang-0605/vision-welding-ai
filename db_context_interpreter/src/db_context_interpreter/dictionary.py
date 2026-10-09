"""b. 문자/기호 DB: 워크스페이스 사전 대조"""
import re
from difflib import SequenceMatcher

from db_context_interpreter.readings import normalize
from db_context_interpreter.welding import parse_thickness

FUZZY_MIN = 0.8          # 유사 일치로 볼 최소 유사도 (difflib ratio)
AMBIGUOUS_MARGIN = 0.2   # 1단계 후보 확률이 이만큼 이내로 붙어 있고 사전 해석이 달라지면 ambiguous_reading
CODE_VALUE = re.compile(r"^([A-Z]+)([0-9]+(?:\.[0-9]+)?)$")  # 코드 + 숫자 (수기 각장 F5.5, V6, S4.5)


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
        """코드 뒤에 숫자가 붙은 표기 (예: F5.5 → F 항목, "3F 용접장 각장 5.5mm")"""
        m = CODE_VALUE.match(normalize(value))
        entry = self.codes.get(m.group(1)) if m else None
        if not entry or entry["kind"] != "text":
            return None
        base, _, note = entry["meaning"].partition("(")
        unit = "mm" if "mm" in note else ""
        return entry, f"{base.strip()} {m.group(2)}{unit}"

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
) -> list[dict]:
    """1단계 글자·기호(작업자가 고친 값 우선)를 context_input["symbols"]의 code·aliases와 대조 → DictionaryMatch 목록.
    skip: 부재 번호로 쓴 표기 (조립 경로 DB에서 해석)

    match: exact 그대로 일치 / alias 별칭 일치 / candidate 1단계 후보 중 하나가 일치 / fuzzy 유사 일치 /
           vlm 사전에 없지만 VLM이 해석 / none 해석 못 함
    """
    dictionary = Dictionary(context_input["symbols"])
    matches = []
    for r in readings:
        if r["ref_id"] in skip:
            continue
        m = match_one(r, dictionary, vlm_meanings.get(r["ref_id"]), vlm_prob)
        if r["meaning"]:  # 작업자가 직접 정한 의미가 사전보다 우선
            m["meaning"] = r["meaning"]
        matches.append(m)
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
            return result(value, found[0], "exact", prob, found[1])
    for candidate, candidate_prob in r["candidates"]:
        if found := dictionary.lookup(candidate) or dictionary.code_with_value(candidate):
            entry, extra = found
            return result(candidate, entry, "candidate", candidate_prob, None if extra in ("exact", "alias") else extra)
    if value != "unknown" and (found := dictionary.fuzzy(value)):
        return result(value, found[0], "fuzzy", prob * found[1])
    if vlm_meaning:
        return result(value, None, "vlm", vlm_prob, vlm_meaning)
    thickness = parse_thickness(value)
    return result(value, None, "none", prob if thickness is not None else 0.0,
                  f"판 두께 {thickness:g}mm" if thickness is not None else None)


def dictionary_conflicts(matches: list[dict], readings: list[dict], context_input: dict) -> list[dict]:
    """dictionary_unmatched(사전에 없음: fuzzy · vlm · none) · ambiguous_reading(후보마다 사전 해석이 달라짐).
    작업자가 고치거나 확인한 표기는 넣지 않음"""
    dictionary = Dictionary(context_input["symbols"])
    corrected = {r["ref_id"] for r in readings if r["corrected"]}
    by_ref = {r["ref_id"]: r for r in readings}
    conflicts = []
    for m in matches:
        ref = m["ref_ids"][0]
        if ref in corrected:
            continue
        raw = m["raw"]
        if m["match"] == "fuzzy":
            conflicts.append(unmatched(f"'{raw}' 표기는 사전에 그대로 없어 비슷한 '{m['code']}'({m['meaning']})로 봄", "info", ref))
        elif m["match"] == "vlm":
            conflicts.append(unmatched(f"'{raw}' 표기는 문자/기호 사전에 없어 VLM 해석({m['meaning']})을 사용함", "info", ref))
        elif m["match"] == "none" and m["meaning"]:
            conflicts.append(unmatched(f"'{raw}' 표기는 문자/기호 사전에 없어 표기 규칙으로 해석함({m['meaning']})", "info", ref))
        elif m["match"] == "none":
            conflicts.append(unmatched(f"'{raw}' 표기는 문자/기호 사전에 없고 해석하지 못함", "warning", ref))

        r = by_ref[ref]
        rivals = [
            (value, p) for value, p in r["candidates"]
            if p >= r["prob"] - AMBIGUOUS_MARGIN
            and (found := dictionary.lookup(value) or dictionary.code_with_value(value))
            and found[0]["code"] != m["code"]
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
