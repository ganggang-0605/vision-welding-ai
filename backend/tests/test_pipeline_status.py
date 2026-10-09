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


def test_status_shows_last_vlm_failure(client, monkeypatch):
    """VLM 이 실패하면 설정 화면에서 바로 알 수 있게 최근 실패 이유를 보여 주고, 다음에 성공하면 지움"""
    import json

    import cv2
    import numpy as np
    from db_context_interpreter import vlm as vlm_module

    def broken(*args):
        raise RuntimeError("authentication_error: invalid x-api-key")

    monkeypatch.setenv("VLM_PROVIDER", "claude")
    monkeypatch.setenv("VLM_RUNS", "1")
    monkeypatch.setitem(vlm_module.PROVIDERS, "claude", broken)
    ok, png = cv2.imencode(".png", np.full((480, 640, 3), 128, np.uint8))
    job = "/workspaces/demo/jobs/job_demo_p1"
    client.post(f"{job}/images", files={"file": ("cell.png", png.tobytes(), "image/png")})
    client.post(f"{job}/analyze")
    status = client.get("/pipeline/status").json()
    assert "invalid x-api-key" in status["vlm_last_error"] and status["vlm_last_error_at"].endswith("Z")
    assert any("VLM 해석이 실패" in m for m in client.get(job).json()["needs_review"])

    response = {"interpretation": "표기 없음", "texts": [], "symbols": [], "meanings": []}
    monkeypatch.setitem(vlm_module.PROVIDERS, "claude", lambda *a: (json.dumps(response), None))
    client.post(f"{job}/analyze")
    assert client.get("/pipeline/status").json()["vlm_last_error"] is None
