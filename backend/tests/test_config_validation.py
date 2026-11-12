import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("max_upload_mb", 0),
        ("ollama_timeout_seconds", 0),
        ("ocr_dpi", 71),
        ("ocr_dpi", 601),
        ("media_crop_margin_pt", -0.1),
        ("media_crop_margin_pt", 72.1),
        ("math_crop_dpi", 601),
    ],
)
def test_invalid_resource_configuration_is_rejected(setting, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{setting: value})


def test_defaults_keep_ollama_disabled_and_ocr_render_settings_bounded():
    settings = Settings(_env_file=None)

    assert settings.ollama_enabled is False
    assert settings.max_upload_mb > 0
    assert 72 <= settings.ocr_dpi <= 600
    assert 72 <= settings.math_crop_dpi <= 600
    assert 0 <= settings.media_crop_margin_pt <= 72
