from io import BytesIO
import fitz
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

def test_scanned_pdf_page_uses_ocr_and_preserves_native_text(tmp_path, monkeypatch):
    source = tmp_path / "scanned.pdf"
    document = fitz.open()
    page = document.new_page(width=300, height=200)

    image = Image.new("RGB", (300, 200), "white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    page.insert_image(page.rect, stream=buffer.getvalue())
    document.save(source)
    document.close()

    def fake_ocr(page, page_number, media_dir):
        rect = fitz.Rect(20, 30, 250, 55)
        lines = [(30, 20, "1. What is artificial intelligence?", rect, [])]
        return "1. What is artificial intelligence?", [], lines

    monkeypatch.setattr(engine, "_ocr_page", fake_ocr)

    result = engine.extract_pdf(source, tmp_path / "media")
    extracted = result["pages"][0]

    assert extracted["needs_ocr"] is True
    assert extracted["ocr_used"] is True
    assert extracted["text"] == "1. What is artificial intelligence?"
    assert extracted["source_text"] == ""

def test_encoding_artifacts_trigger_ocr_replacement(tmp_path, monkeypatch):
    source = tmp_path / "legacy-font.pdf"
    document = fitz.open()
    page = document.new_page(width=300, height=200)

    font_path = r"C:\Windows\Fonts\arial.ttf"
    page.insert_font(fontname="ArialUnicode", fontfile=font_path)
    page.insert_text(
        (20, 50),
        "tÂ² + aâƒ— = corrupted native text",
        fontname="ArialUnicode",
        fontsize=12,
    )

    document.save(source)
    document.close()

    def fake_ocr(page, page_number, media_dir):
        rect = fitz.Rect(20, 30, 250, 55)
        lines = [(30, 20, "t² + a⃗ = correct OCR text", rect, [])]
        return "t² + a⃗ = correct OCR text", [], lines

    monkeypatch.setattr(engine, "_ocr_page", fake_ocr)

    result = engine.extract_pdf(source, tmp_path / "media")
    extracted = result["pages"][0]

    assert extracted["needs_ocr"] is True
    assert extracted["ocr_used"] is True
    assert extracted["source_text"].strip() == extracted["native_text"].strip()
    assert "correct OCR text" in extracted["text"]
    assert "corrupted native text" in " ".join(extracted["source_text"].split())

def test_good_native_text_is_not_replaced_by_ocr(tmp_path, monkeypatch):
    source = tmp_path / "good-native.pdf"
    document = fitz.open()
    page = document.new_page(width=400, height=300)

    page.insert_font(
        fontname="ArialUnicode",
        fontfile=r"C:\Windows\Fonts\arial.ttf",
    )
    page.insert_text(
        (30, 50),
        "Question 1: What is artificial intelligence?",
        fontname="ArialUnicode",
        fontsize=12,
    )
    page.insert_text(
        (30, 80),
        "A. Machine learning  B. Natural intelligence",
        fontname="ArialUnicode",
        fontsize=12,
    )

    document.save(source)
    document.close()

    ocr_called = {"value": False}

    def fake_ocr(page, page_number, media_dir):
        ocr_called["value"] = True
        rect = fitz.Rect(20, 30, 350, 55)
        lines = [(30, 20, "Incorrect OCR replacement", rect, [])]
        return "Incorrect OCR replacement", [], lines

    monkeypatch.setattr(engine, "_ocr_page", fake_ocr)

    result = engine.extract_pdf(source, tmp_path / "media")
    extracted = result["pages"][0]

    assert extracted["needs_ocr"] is False
    assert extracted["ocr_used"] is False
    assert ocr_called["value"] is False
    normalized_text = " ".join(extracted["text"].split())
    assert "What is artificial intelligence?" in normalized_text