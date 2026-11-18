from __future__ import annotations

from autoapplication.core.documents import collect, describe
from autoapplication.core.text import format_workload, haversine_km, parse_date


def test_collect_sorts_cv_first_and_skips_other_files(tmp_path) -> None:
    (tmp_path / "zeugnisse").mkdir()
    (tmp_path / "zeugnisse" / "zeugnis_2024.pdf").write_bytes(b"x")
    (tmp_path / "lebenslauf.pdf").write_bytes(b"x")
    (tmp_path / "notiz.txt").write_bytes(b"x")
    (tmp_path / ".versteckt.pdf").write_bytes(b"x")
    files = collect(tmp_path)
    names = [path.name for path in files]
    assert names[0] == "lebenslauf.pdf"
    assert "zeugnis_2024.pdf" in names
    assert "notiz.txt" not in names
    assert ".versteckt.pdf" not in names


def test_collect_limits_total_size(tmp_path) -> None:
    (tmp_path / "gross.pdf").write_bytes(b"0" * (2 * 1024 * 1024))
    (tmp_path / "klein.pdf").write_bytes(b"0" * 1024)
    files = collect(tmp_path, max_mb=1)
    # Die zu grosse Datei faellt weg, die kleine bleibt.
    assert [path.name for path in files] == ["klein.pdf"]


def test_collect_disabled_or_missing(tmp_path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"x")
    assert collect(tmp_path, enabled=False) == []
    assert collect(tmp_path / "gibt-es-nicht") == []
    assert collect("") == []


def test_describe() -> None:
    assert describe([]) == "keine Anhaenge"
    from pathlib import Path

    assert "a.pdf" in describe([Path("a.pdf"), Path("b.pdf")])


def test_format_workload() -> None:
    assert format_workload(100, 100) == "100 %"
    assert format_workload(80, 100) == "80-100 %"
    assert format_workload(0, 0) == ""
    assert format_workload(100, 80) == "80-100 %"


def test_haversine() -> None:
    distance = haversine_km(47.4055, 9.6087, 47.4912, 9.5555)
    assert distance is not None
    assert 8 < distance < 12
    assert haversine_km("x", 9.6, 47.4, 9.6) is None


def test_parse_date_variants() -> None:
    assert parse_date("2026-11-18").isoformat() == "2026-11-18"
    assert parse_date("18.11.2026").isoformat() == "2026-11-18"
    assert parse_date("2026-07-30T15:06:55.000+02:00").isoformat() == "2026-07-30"
    assert parse_date("2026-11-06 15:06:55.000000+0200").isoformat() == "2026-11-06"
    assert parse_date("") is None
    assert parse_date("kein Datum") is None
