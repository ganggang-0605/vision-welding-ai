import os

import pytest

# 테스트는 실제 VLM API 를 부르지 않음 (.env 보다 먼저 정해서 덮어쓰지 않게). VLM 을 켜는 테스트는 monkeypatch 로
os.environ["VLM_PROVIDER"] = "off"
os.environ["PRELOAD_MODELS"] = "0"  # 시작할 때 OCR 모델을 미리 불러오지 않음
from fastapi.testclient import TestClient

from app.main import app
from app.store import reset_store


@pytest.fixture(autouse=True)
def fresh_store():
    """테스트마다 인메모리 저장소를 시드 상태(데모 워크스페이스)로 초기화해 서로 격리한다 (최근 VLM 실패 기록도)."""
    import app.pipeline as pipeline

    pipeline._vlm_state.update(error=None, at=None)
    return reset_store()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
