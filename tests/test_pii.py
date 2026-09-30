from app.pii import scrub_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_cccd() -> None:
    out = scrub_text("CCCD cua toi la 001203004567")
    assert "001203004567" not in out
    assert "REDACTED_CCCD" in out


def test_scrub_credit_card_formats() -> None:
    for card in ("4111111111111111", "4111 1111 1111 1111", "4111-0123-4567-8901"):
        out = scrub_text(f"Card: {card}")
        assert card not in out
        assert "REDACTED_CREDIT_CARD" in out
        assert "REDACTED_PHONE_VN" not in out


def test_scrub_passport() -> None:
    out = scrub_text("Passport C1234567")
    assert "C1234567" not in out
    assert "REDACTED_PASSPORT" in out


def test_scrub_keeps_normal_text() -> None:
    text = "Giai thich P95 latency va SLO 99.5% cho 2025"
    assert scrub_text(text) == text


def test_scrub_event_covers_nested_and_top_level_fields() -> None:
    from app.logging_config import scrub_event

    out = scrub_event(
        None,
        "info",
        {
            "event": "request_failed",
            "exception": "ValueError: bad input a@b.com",
            "payload": {"detail": "call 0901234567", "items": ["x@y.vn"]},
        },
    )
    rendered = str(out)
    assert "a@b.com" not in rendered
    assert "0901234567" not in rendered
    assert "x@y.vn" not in rendered
