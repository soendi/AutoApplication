from datetime import datetime, timedelta

from autoapplication.ui.main_window import mail_countdown_text

NOW = datetime(2026, 11, 19, 12, 0, 0)


def test_countdown_in_minutes() -> None:
    assert mail_countdown_text(NOW + timedelta(minutes=42), NOW) == (
        "Postfach-Abruf in 42 Min."
    )


def test_countdown_in_hours_and_minutes() -> None:
    assert mail_countdown_text(NOW + timedelta(hours=3, minutes=12), NOW) == (
        "Postfach-Abruf in 3 Std. 12 Min."
    )


def test_countdown_next_day() -> None:
    assert mail_countdown_text(NOW + timedelta(days=1, hours=5), NOW) == (
        "Postfach-Abruf in 1 Tg. 05 Std."
    )


def test_countdown_about_to_start() -> None:
    assert mail_countdown_text(NOW + timedelta(seconds=20), NOW) == (
        "Postfach-Abruf in Kürze"
    )
