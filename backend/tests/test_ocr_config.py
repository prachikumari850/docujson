from io import BytesIO

from PIL import Image

from app.config import settings
from app.services import engine


class FakePixmap:
    def tobytes(self, _format):
        image = Image.new("RGB", (80, 40), "white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


class FakePage:
    def get_pixmap(self, **_kwargs):
        return FakePixmap()


def test_ocr_falls_back_to_english_when_hindi_data_is_missing(tmp_path, monkeypatch):
    selected = {}
    monkeypatch.setattr(settings, "tesseract_cmd", "")
    monkeypatch.setattr(settings, "tessdata_prefix", None)
    monkeypatch.setattr(settings, "ocr_languages", "eng+hin")
    monkeypatch.setattr(engine.pytesseract, "get_tesseract_version", lambda: "5.0")
    monkeypatch.setattr(engine.pytesseract, "get_languages", lambda config="": ["eng", "osd"])

    def fake_image_to_data(_image, lang, **kwargs):
        selected["lang"] = lang
        return {"text": ["native"], "conf": ["90"], "page_num": [1], "block_num": [1], "par_num": [1], "line_num": [1], "left": [8], "top": [8], "width": [30], "height": [10]}

    monkeypatch.setattr(engine.pytesseract, "image_to_data", fake_image_to_data)
    text, warnings, lines = engine._ocr_page(FakePage(), 1, tmp_path)

    assert text == "native"
    assert selected["lang"] == "eng"
    assert any("hin" in warning for warning in warnings)
    assert (tmp_path / "evidence_page_1.png").is_file()
    assert lines[0][2] == "native"


def test_ocr_reports_unavailable_tesseract(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "tesseract_cmd", "missing-tesseract.exe")

    def unavailable():
        raise OSError("not installed")

    monkeypatch.setattr(engine.pytesseract, "get_tesseract_version", unavailable)
    text, warnings, lines = engine._ocr_page(FakePage(), 1, tmp_path)

    assert text == ""
    assert not lines
    assert any("OCR unavailable" in warning for warning in warnings)
