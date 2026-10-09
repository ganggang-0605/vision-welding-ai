"""JSON 스키마 읽기와 검증"""
import json
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

SHARED = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = SHARED / "schemas"
EXAMPLES_DIR = SHARED / "examples"
BASE = "https://vision-welding-ai.local/shared/schemas/"


@cache
def registry() -> Registry:
    """shared/schemas의 모든 스키마 ($ref로 서로 참조)"""
    resources = []
    for path in sorted(SCHEMAS_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["$id"] == BASE + path.name, f"{path.name}: $id가 파일 이름과 다름"
        Draft202012Validator.check_schema(schema)
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources)


def schema_errors(instance, name: str) -> list[str]:
    """instance가 스키마 파일 name(예: "vision_result.schema.json")에 맞지 않는 곳. 맞으면 빈 목록"""
    validator = Draft202012Validator({"$ref": BASE + name}, registry=registry(), format_checker=FormatChecker())
    return [
        f"{'/'.join(map(str, e.absolute_path)) or '(최상위)'}: {e.message}"
        for e in validator.iter_errors(instance)
    ]


def load_example(name: str) -> dict:
    """shared/examples의 예시 (예: "vision_result.example.json"). 각 단계 테스트의 입력으로 씀"""
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))
