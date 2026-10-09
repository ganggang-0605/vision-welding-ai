"""파이프라인 공용 패키지 — shared/schemas의 JSON 스키마를 기준으로 단계 사이 데이터를 다룸

스키마 파일은 저장소의 shared/schemas를 그대로 읽으므로 editable 설치(pip install -e shared)로 씀.
"""
from vw_shared.ids import is_ref, vlm_only
from vw_shared.job_fields import CONFIDENCE_FIELDS, WELDING_CONDITION_FIELDS, latest_analysis, to_job_fields
from vw_shared.rules import semantic_errors
from vw_shared.schemas import EXAMPLES_DIR, SCHEMAS_DIR, load_example, schema_errors

__all__ = [
    "CONFIDENCE_FIELDS", "EXAMPLES_DIR", "SCHEMAS_DIR", "WELDING_CONDITION_FIELDS",
    "is_ref", "latest_analysis", "load_example", "schema_errors", "semantic_errors", "to_job_fields", "vlm_only",
]
