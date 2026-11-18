"""Startpunkt der Anwendung."""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from . import APP_NAME, APP_VERSION
from .core.config import Settings, ensure_home, log_path


def _configure_logging() -> None:
    ensure_home()
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        handlers.append(logging.FileHandler(log_path(), encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    for name in ("urllib3", "PySide6"):
        logging.getLogger(name).setLevel(logging.WARNING)


def _self_test() -> int:
    """Kurztest ohne Oberflaeche und ohne Netz."""
    from .core.ai import AiClient, classify_local
    from .core.models import Job
    from .core.ostjob import parse_vacancy
    from .core.pipeline import Pipeline, due_label
    from .core.store import Store
    from .core.templates import choose_template, load_defaults, render_mail
    from .core.text import now_iso
    from .core.updater import Release, asset_for, is_newer, release_page

    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(Path(tmp) / "einstellungen.json")
        settings.set("profile.vorname", "Erika")
        settings.set("profile.nachname", "Muster")
        settings.set("profile.erfahrung_jahre", "acht")
        settings.save()
        assert settings.load().text("profile.nachname") == "Muster"

        store = Store(Path(tmp) / "daten.db")
        job = Job(
            id="ostjob:1",
            source="ostjob",
            source_id="1",
            title="Speditionskaufmann Disposition",
            company="Muster Logistik AG",
            city="Balgach",
            workload="80-100 %",
            description="Disposition, Transport und Lager",
            keywords=["Spedition", "Disposition", "Transport"],
        )
        assert store.upsert_job(job, now=now_iso()) is True
        assert store.upsert_job(job, now=now_iso()) is False

        parsed = parse_vacancy(
            {
                "id": 99,
                "title": "Lagermitarbeiter <b>Logistik</b>",
                "typeValueMin": 80,
                "typeValueMax": 100,
                "keywords": "Lager, Logistik",
                "company": {"name": "Beispiel AG", "homepage": "https://beispiel.ch"},
                "coordinates": [{"latitude": 47.4, "longitude": 9.6}],
            },
            home=(47.4055, 9.6087),
        )
        assert parsed.company == "Beispiel AG"
        assert parsed.workload == "80-100 %"
        assert parsed.distance_km is not None
        assert "<b>" not in parsed.title

        templates = load_defaults()
        template, score, matches = choose_template(templates, job, job.keywords, 2)
        assert template is not None and template.id == "spedition", (template, score)
        subject, body = render_mail(template, settings.profile(), job)
        assert "{firma}" not in body and "Muster Logistik AG" in body
        assert "{vorname}" not in body and "Erika" in body
        assert subject

        assert classify_local("Ihre Bewerbung", "Leider müssen wir Ihnen eine Absage erteilen.") == "absage"
        assert classify_local("Ihre Bewerbung", "Wir freuen uns auf ein Vorstellungsgespräch.") == "einladung"

        application = store.add_application(
            job.id,
            template.id,
            subject,
            body,
            status="gesendet",
            created_at=now_iso(),
        )
        store.update_application(
            application, sent_at=(date.today() - timedelta(days=15)).isoformat()
        )
        due = store.due_follow_ups(14)
        assert due, "Nach 15 Tagen muss eine Nachfrage fällig sein"
        assert due_label(due[0], 14) == "fällig"

        pipeline = Pipeline(settings, store, templates_file=Path(tmp) / "vorlagen.json")
        assert pipeline.templates(), "Vorlagen müssen geladen werden"
        assert AiClient(settings).available() is False

        assert is_newer("0.9.9", "1.0.0")
        assert not is_newer("1.0.0", "1.0.0")
        release = Release(
            version="1.0.0",
            tag="v1.0.0",
            assets={"AutoApplication-1.0.0-Setup.exe": "https://example.invalid/x"},
        )
        assert asset_for(release, "win32") is not None
        assert asset_for(release, "linux") is None
        assert release_page().startswith("https://github.com/")

        print(
            f"SELFTEST OK - {len(templates)} Vorlagen, "
            f"Passung {score} ({', '.join(matches[:3])}), "
            f"{len(store.events())} Protokolleinträge"
        )
    return 0


def _apply_update(argv: list[str]) -> int:
    """Wartet auf das Ende des alten Fensters und startet dann das Setup."""
    from .core.updater import launch_installer, wait_for_exit

    index = argv.index("--apply-update")
    if index + 1 >= len(argv):
        return 2
    archive = Path(argv[index + 1])
    pid = 0
    if "--wait-pid" in argv:
        try:
            pid = int(argv[argv.index("--wait-pid") + 1])
        except (IndexError, ValueError):
            pid = 0
    if pid:
        wait_for_exit(pid)
    if not launch_installer(archive):
        return 3
    return 0


def _run_daily() -> int:
    """Tageslauf ohne Fenster (z. B. aus der Windows-Aufgabenplanung)."""
    from .core.config import database_path
    from .core.pipeline import Pipeline
    from .core.store import Store

    settings = Settings().load()
    store = Store(database_path())
    pipeline = Pipeline(settings, store, notifier=_print_notice)
    summary = pipeline.run_daily()
    print(summary.as_text())
    return 0


def _print_notice(title: str, message: str) -> None:
    print(f"{title}: {message}")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    _configure_logging()

    if "--version" in argv:
        print(f"{APP_NAME} {APP_VERSION}")
        return 0
    if "--self-test" in argv:
        return _self_test()
    if "--apply-update" in argv:
        return _apply_update(argv)
    if "--run-daily" in argv:
        return _run_daily()

    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    from PySide6.QtWidgets import QApplication

    from .core.config import database_path
    from .core.pipeline import Pipeline
    from .core.store import Store
    from .ui.branding import app_icon
    from .ui.main_window import MainWindow
    from .ui.theme import apply_theme

    ensure_home()
    settings = Settings().load()
    if not settings.path.exists():
        settings.save()
    store = Store(database_path())

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_NAME)
    app.setWindowIcon(app_icon())
    apply_theme(app)

    pipeline = Pipeline(settings, store)
    window = MainWindow(settings=settings, store=store, pipeline=pipeline)
    pipeline.notifier = window.notify
    window.show()

    if "--no-update" not in argv and os.environ.get("AUTOAPPLICATION_NO_UPDATE") != "1":
        window.start_auto_update()
    window.maybe_start_daily()

    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
