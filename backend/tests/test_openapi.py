"""OpenAPI 문서(/docs, 생성 클라이언트)가 실제 동작·API 계약과 맞는지"""
import pytest

from app.main import app

OPENAPI = app.openapi()
SCHEMAS = OPENAPI["components"]["schemas"]
ERROR_DETAIL = {"$ref": "#/components/schemas/ErrorDetail"}


def _error_schema(path: str, method: str, code: str) -> dict:
    return OPENAPI["paths"][path][method]["responses"][code]["content"]["application/json"]["schema"]


@pytest.mark.parametrize("name", [
    "Workspace", "SymbolEntry", "AssemblyNode", "Job", "Marking", "WeldingCondition", "Confidence", "WeldingStandard",
])
def test_response_fields_required(name):
    """응답 JSON 에는 기본값이 있는 필드도 항상 들어 있다 → 응답 스키마에서 모두 필수"""
    assert set(SCHEMAS[name]["required"]) == set(SCHEMAS[name]["properties"])


def test_request_defaults_optional():
    assert SCHEMAS["JobCreate"]["required"] == ["name"]
    assert SCHEMAS["WorkspaceCreate"]["required"] == ["name"]


def test_symbol_update_nullability():
    """PATCH 본문에서 null 을 받는 필드는 welding_joint_type 뿐"""
    props = SCHEMAS["SymbolEntryUpdate"]["properties"]
    nullable = {name for name, prop in props.items() if {"type": "null"} in prop.get("anyOf", [])}
    assert nullable == {"welding_joint_type"}


def test_error_responses_documented():
    workspace_paths = [p for p in OPENAPI["paths"] if p.startswith("/workspaces/{workspace_id}")]
    assert workspace_paths
    for path in workspace_paths:
        for method in OPENAPI["paths"][path]:
            assert _error_schema(path, method, "404") == ERROR_DETAIL, (method, path)
    assert _error_schema("/workspaces", "post", "404") == ERROR_DETAIL  # 복사할 사전의 워크스페이스
    jobs = "/workspaces/{workspace_id}/jobs/{job_id}"
    for method, path, code in [("post", f"{jobs}/approve", "409"), ("get", f"{jobs}/export", "409"),
                               ("post", f"{jobs}/analyze", "501")]:
        assert _error_schema(path, method, code) == ERROR_DETAIL
