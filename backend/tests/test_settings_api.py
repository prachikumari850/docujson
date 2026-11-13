import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 75)
    monkeypatch.setattr(settings, "ocr_languages", "eng+hin")
    monkeypatch.setattr(settings, "ocr_dpi", 300)
    monkeypatch.setattr(settings, "media_crop_margin_pt", 6.0)
    monkeypatch.setattr(settings, "math_crop_dpi", 288)
    monkeypatch.setattr(settings, "ollama_enabled", False)

    with TestClient(app) as test_client:
        yield test_client


def test_get_settings_returns_safe_configuration(client):
    response = client.get("/api/settings")

    assert response.status_code == 200

    data = response.json()

    assert data["upload"] == {
        "max_size_mb": 75,
        "supported_formats": ["docx", "pdf", "txt"],
    }

    assert data["storage"] == {
        "type": "local",
    }

    assert data["ocr"] == {
        "languages": "eng+hin",
        "dpi": 300,
    }

    assert data["extraction"] == {
        "media_crop_margin_pt": 6.0,
        "math_crop_dpi": 288,
    }

    assert data["ai"] == {
        "provider": "ollama",
        "enabled": False,
        "model": None,
    }


def test_get_settings_does_not_expose_internal_paths_or_urls(client):
    response = client.get("/api/settings")

    assert response.status_code == 200

    data = response.json()

    assert "storage_dir" not in str(data)
    assert "storage_path" not in str(data)
    assert "ollama_base_url" not in str(data)
