import httpx
import pytest

from app.config import settings
from app.services import engine, vision


class FakeResponse:
    status_code = 200

    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.request = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, url, json):
        self.request = (url, json)
        return self.response


def test_ollama_visual_request_uses_image_payload_and_returns_candidate_only(tmp_path, monkeypatch):
    image = tmp_path / "crop.png"
    image.write_bytes(b"test-image-bytes")
    client = FakeClient(FakeResponse({"model": "qwen2.5vl:3b", "response": "(1) t^2", "done": True}))
    monkeypatch.setattr(vision.httpx, "Client", lambda **_kwargs: client)

    result = vision.verify_math_image(image, base_url="http://localhost:11434/", model="qwen2.5vl:3b", timeout_seconds=2)

    assert client.request[0] == "http://localhost:11434/api/generate"
    assert client.request[1]["images"]
    assert result["candidate_transcription"] == "(1) t^2"
    assert result["trusted_as_extracted_text"] is False


def test_ollama_invalid_or_incomplete_response_is_rejected(tmp_path, monkeypatch):
    image = tmp_path / "crop.png"
    image.write_bytes(b"test-image-bytes")
    monkeypatch.setattr(vision.httpx, "Client", lambda **_kwargs: FakeClient(FakeResponse({"response": "", "done": False})))

    with pytest.raises(ValueError, match="incomplete or empty"):
        vision.verify_math_image(image, base_url="http://localhost:11434", model="qwen2.5vl:3b", timeout_seconds=2)


def test_ollama_disabled_is_a_no_call_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ollama_enabled", False)
    monkeypatch.setattr(engine, "verify_math_image", lambda *_args, **_kwargs: pytest.fail("disabled Ollama must not be called"))
    monkeypatch.setattr(httpx, "get", lambda *_args, **_kwargs: pytest.fail("disabled Ollama must not be queried"))

    result = engine.verify_suspicious_option_crops([], tmp_path)

    assert result == {"enabled": False, "available": False, "model": None, "used": False, "regions_attempted": 0, "regions_completed": 0, "warnings": []}


def test_ollama_timeout_is_reported_without_failing_conversion(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ollama_enabled", True)
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5vl:3b")
    monkeypatch.setattr(engine.httpx if hasattr(engine, "httpx") else httpx, "get", lambda *_args, **_kwargs: FakeResponse({"models": [{"name": "qwen2.5vl:3b"}]}))
    crop = tmp_path / "option.png"
    crop.write_bytes(b"crop")
    monkeypatch.setattr(engine, "verify_math_image", lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.ReadTimeout("slow")))
    sections = [{"questions": [{"question_number": 3, "review_required": True, "review_reasons": [], "options": [{"id": "2", "text": "x2", "media": [{"type": "option_crop", "filename": crop.name}], "review_reasons": [], "review_required": True}]}]}]

    result = engine.verify_suspicious_option_crops(sections, tmp_path)

    assert result["available"] is True
    assert result["used"] is False
    assert result["regions_attempted"] == 1
    assert any("ReadTimeout" in warning for warning in result["warnings"])
    assert sections[0]["questions"][0]["options"][0]["text"] == "x2"
