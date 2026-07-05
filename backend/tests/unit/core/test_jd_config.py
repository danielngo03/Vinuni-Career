from app.core.config import get_settings


def test_jd_engine_defaults_present():
    s = get_settings()
    assert s.jd_vision_extraction_enabled is True
    assert s.jd_vision_provider_alias == "vision_default"
    assert s.jd_llm_structuring_provider_alias == "chat_default"
    assert s.jd_ocr_langs == "vie+eng"
    assert s.jd_vision_max_pages == 3
    assert s.jd_vision_max_image_px == 2200
    assert s.jd_max_upload_bytes == 10 * 1024 * 1024
