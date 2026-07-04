"""Unit tests for the language detection heuristic.

All tests are pure-function, no I/O, no DB, no external ML dependencies.
Covers: Vietnamese detection, English detection, CJK detection, mixed,
unknown (short text), and real-world JD patterns.
"""

from __future__ import annotations

import pytest

from app.modules.opportunities.domain.language_detection import detect_language


# ---------------------------------------------------------------------------
# Vietnamese detection
# ---------------------------------------------------------------------------


def test_vi_heavy_text() -> None:
    text = (
        "Chúng tôi đang tìm kiếm một kỹ sư phần mềm có kinh nghiệm làm việc "
        "với Python và các công nghệ cloud hiện đại. Ứng viên cần có kỹ năng "
        "giao tiếp tốt và có khả năng làm việc nhóm hiệu quả trong môi trường "
        "phát triển phần mềm Agile."
    )
    assert detect_language(text) == "vi"


def test_vi_jd_sample() -> None:
    text = (
        "Mô tả công việc: Thiết kế và phát triển các hệ thống phần mềm quy mô "
        "lớn. Yêu cầu ứng viên: Tốt nghiệp đại học chuyên ngành CNTT, có ít "
        "nhất 2 năm kinh nghiệm. Quyền lợi: Mức lương cạnh tranh, thưởng theo "
        "hiệu quả công việc, bảo hiểm sức khỏe cao cấp."
    )
    assert detect_language(text) == "vi"


# ---------------------------------------------------------------------------
# English detection
# ---------------------------------------------------------------------------


def test_en_pure_latin() -> None:
    text = (
        "We are looking for a backend software engineer with strong experience "
        "in Python, PostgreSQL, and cloud infrastructure. You will design and "
        "build scalable distributed systems and collaborate closely with the "
        "product team to deliver high-quality features."
    )
    assert detect_language(text) == "en"


def test_en_tech_jd() -> None:
    text = (
        "Requirements: 3+ years of experience with React and TypeScript. "
        "Strong understanding of REST APIs and microservices architecture. "
        "Experience with Docker, Kubernetes, and CI/CD pipelines. "
        "Benefits: Competitive salary, health insurance, flexible working hours."
    )
    assert detect_language(text) == "en"


# ---------------------------------------------------------------------------
# Mixed Vietnamese/English detection
# ---------------------------------------------------------------------------


def test_mixed_vi_en() -> None:
    # Vietnamese intro with heavy English skill names — typical real-world JD
    text = (
        "Chúng tôi cần tuyển dụng Python developer với kinh nghiệm về "
        "microservices architecture và cloud platforms. Yêu cầu thành thạo "
        "Docker, Kubernetes, PostgreSQL."
    )
    result = detect_language(text)
    assert result in ("vi", "mixed"), f"Expected vi or mixed, got {result!r}"


# ---------------------------------------------------------------------------
# CJK script detection
# ---------------------------------------------------------------------------


def test_zh_detected() -> None:
    text = "我们正在寻找一名经验丰富的软件工程师加入我们的团队。" * 5
    assert detect_language(text) == "zh"


def test_ja_detected() -> None:
    text = "ソフトウェアエンジニアを募集しています。経験者優遇します。" * 5
    assert detect_language(text) == "ja"


def test_ko_detected() -> None:
    text = "저희 회사에서 백엔드 개발자를 모집합니다. 경력자 우대합니다." * 5
    assert detect_language(text) == "ko"


# ---------------------------------------------------------------------------
# Unknown / edge cases
# ---------------------------------------------------------------------------


def test_unknown_empty_string() -> None:
    assert detect_language("") == "unknown"


def test_unknown_too_short() -> None:
    assert detect_language("Xin chào") == "unknown"


def test_unknown_none_like_whitespace() -> None:
    assert detect_language("   ") == "unknown"


def test_unknown_numbers_only() -> None:
    # Only digits — no alpha chars
    assert detect_language("1234567890 1234567890 1234567890") == "unknown"


def test_unknown_exactly_19_chars() -> None:
    # Threshold is 20 chars stripped
    assert detect_language("abcdefghijklmnopqrs") == "unknown"


def test_en_exactly_20_chars() -> None:
    # 20 chars — should attempt detection (returns en for pure Latin)
    result = detect_language("abcdefghijklmnopqrst")
    assert result == "en"


# ---------------------------------------------------------------------------
# Boundary / regression
# ---------------------------------------------------------------------------


def test_vi_boundary_ratio_above_threshold() -> None:
    # Enough Vietnamese diacritics to hit the 0.08 threshold
    vi_heavy = "àáâãèéêìí " * 20
    result = detect_language(vi_heavy)
    assert result == "vi"


def test_mixed_boundary_ratio_between_thresholds() -> None:
    # A small amount of Vietnamese diacritics mixed with lots of Latin
    # vi_ratio should be between 0.02 and 0.08 → "mixed"
    mixed = "a" * 100 + "à" * 3  # vi_ratio ≈ 0.03 / 0.103 ≈ 0.029
    result = detect_language(mixed + " " * 5)  # pad to ensure >20 chars
    assert result == "mixed"
