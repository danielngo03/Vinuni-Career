from __future__ import annotations

from app.shared import config


def test_gemini_api_keys_use_gemini_api_key_comma_separated_value(monkeypatch):
    monkeypatch.setattr(
        config,
        "_collect_dotenv_values",
        lambda: {
            "GEMINI_API_KEY": "key-1, key-2,key-3",
        },
    )
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    assert config.get_gemini_api_keys() == ["key-1", "key-2", "key-3"]
