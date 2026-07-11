from app.ai.extraction.jd import vision as jdv
from app.ai.extraction.text_extraction import FileKind


class _FakeAdapter:
    available = True

    def extract(self, data, kind, *, max_image_px, max_pages, native_text=None):
        return {"is_jd": True, "title": "Sales Executive", "employment_type": "full_time"}


def teardown_function():
    jdv.set_jd_vision_adapter(None)


def test_run_uses_injected_adapter_when_enabled():
    jdv.set_jd_vision_adapter(_FakeAdapter())
    out = jdv.run_jd_vision_extraction(
        b"\xff\xd8\xff", FileKind.IMAGE, enabled=True, max_image_px=2200, max_pages=3
    )
    assert out["title"] == "Sales Executive"


def test_run_returns_none_when_disabled():
    jdv.set_jd_vision_adapter(_FakeAdapter())
    assert (
        jdv.run_jd_vision_extraction(
            b"\xff\xd8\xff", FileKind.IMAGE, enabled=False, max_image_px=2200, max_pages=3
        )
        is None
    )


def test_disabled_default_adapter_is_unavailable():
    jdv.set_jd_vision_adapter(jdv.DisabledJdVisionAdapter())
    assert (
        jdv.run_jd_vision_extraction(
            b"\xff\xd8\xff", FileKind.IMAGE, enabled=True, max_image_px=2200, max_pages=3
        )
        is None
    )
