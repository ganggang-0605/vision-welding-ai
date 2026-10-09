"""GET /pipeline/status — 단계별 모델·API 연결 상태 (API 키 값은 돌려주지 않음)"""
import pytest


@pytest.fixture
def env(monkeypatch):
    for name in ("VLM_PROVIDER", "VLM_MODEL", "VLM_RUNS", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_status_vlm_off(client, env):
    env.setenv("VLM_PROVIDER", "off")
    body = client.get("/pipeline/status").json()
    assert body["vlm_provider"] is None and body["vlm_model"] is None
    assert body["vlm_api_key_set"] is False
    assert body["symbol_detector_available"] is False
    assert isinstance(body["ocr_available"], bool)
    assert body["confidence_threshold"] == 80


def test_status_claude_key_not_leaked(client, env):
    env.setenv("VLM_PROVIDER", "claude  # 주석")
    env.setenv("ANTHROPIC_API_KEY", "sk-secret-value")
    env.setenv("VLM_RUNS", "1")
    res = client.get("/pipeline/status")
    body = res.json()
    assert (body["vlm_provider"], body["vlm_model"], body["vlm_runs"]) == ("claude", "claude-opus-5-5", 1)
    assert body["vlm_api_key_set"] is True
    assert "sk-secret-value" not in res.text


def test_status_missing_key(client, env):
    env.setenv("VLM_PROVIDER", "gemini")
    env.setenv("VLM_MODEL", "gemini-custom")
    body = client.get("/pipeline/status").json()
    assert (body["vlm_provider"], body["vlm_model"], body["vlm_api_key_set"]) == ("gemini", "gemini-custom", False)
