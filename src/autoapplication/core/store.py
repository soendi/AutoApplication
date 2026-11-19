"""SQLite-Ablage: Stellen, Bewerbungen, Antworten, Protokoll.

Jede Operation oeffnet eine eigene Verbindung - damit laesst sich die Ablage
aus dem Oberflaechen-Thread und aus Hintergrundlaeufen zugleich benutzen.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterator

from .models import Job
from .text import parse_date

JOB_FIELDS = {
    "title",
    "company",
    "city",
    "zip",
    "street",
    "canton",
    "workload",
    "url",
    "published",
    "description",
    "keywords",
    "distance_km",
    "score",
    "status",
    "template_id",
    "contact_email",
    "contact_name",
    "contact_tried_at",
    "contact_tried_for",
    "has_form",
    "form_checked",
    "expiry_checked_at",
    "last_seen",
}

APPLICATION_FIELDS = {
    "created_at",
    "tracking",
    "status",
    "sent_at",
    "last_reply_at",
    "reply_kind",
    "reply_note",
    "follow_up_at",
    "follow_up_sent_at",
    "archived_at",
    "draft_id",
    "conversation_id",
    "web_link",
    "internet_message_id",
    "subject",
    "body",
    "template_id",
    "follow_up_subject",
    "follow_up_body",
    "follow_up_draft_id",
    "follow_up_conversation_id",
    "follow_up_web_link",
}

# Wird die Formularerkennung erweitert, steigt diese Nummer und bereits
# gepruefte Stellen ohne Formular werden noch einmal nachgesehen.
FORM_CHECK_VERSION = "3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '',
    zip TEXT NOT NULL DEFAULT '',
    street TEXT NOT NULL DEFAULT '',
    canton TEXT NOT NULL DEFAULT '',
    workload TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    published TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    keywords TEXT NOT NULL DEFAULT '[]',
    distance_km REAL,
    first_seen TEXT NOT NULL DEFAULT '',
    last_seen TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'neu',
    score INTEGER NOT NULL DEFAULT 0,
    template_id TEXT NOT NULL DEFAULT '',
    contact_email TEXT NOT NULL DEFAULT '',
    contact_name TEXT NOT NULL DEFAULT '',
    contact_tried_at TEXT NOT NULL DEFAULT '',
    contact_tried_for TEXT NOT NULL DEFAULT '',
    has_form INTEGER NOT NULL DEFAULT 0,
    form_checked INTEGER NOT NULL DEFAULT 0,
    expiry_checked_at TEXT NOT NULL DEFAULT '',
    raw TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    template_id TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    draft_id TEXT NOT NULL DEFAULT '',
    conversation_id TEXT NOT NULL DEFAULT '',
    web_link TEXT NOT NULL DEFAULT '',
    tracking TEXT NOT NULL DEFAULT '',
    internet_message_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'entwurf',
    created_at TEXT NOT NULL DEFAULT '',
    sent_at TEXT NOT NULL DEFAULT '',
    last_reply_at TEXT NOT NULL DEFAULT '',
    reply_kind TEXT NOT NULL DEFAULT '',
    reply_note TEXT NOT NULL DEFAULT '',
    follow_up_at TEXT NOT NULL DEFAULT '',
    follow_up_sent_at TEXT NOT NULL DEFAULT '',
    follow_up_subject TEXT NOT NULL DEFAULT '',
    follow_up_body TEXT NOT NULL DEFAULT '',
    follow_up_draft_id TEXT NOT NULL DEFAULT '',
    follow_up_conversation_id TEXT NOT NULL DEFAULT '',
    follow_up_web_link TEXT NOT NULL DEFAULT '',
    archived_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    message_id TEXT NOT NULL UNIQUE,
    received_at TEXT NOT NULL DEFAULT '',
    sender TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT '',
    snippet TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    seen INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
"""


class Store:
    """Ablage unter ``daten.db``."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)
            self._migrate(db)

    @staticmethod
    def _migrate(db: sqlite3.Connection) -> None:
        """Fehlende Spalten in bestehenden Ablagen nachruesten."""
        columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
        if "contact_name" not in columns:
            db.execute(
                "ALTER TABLE jobs ADD COLUMN contact_name TEXT NOT NULL DEFAULT ''"
            )
        if "street" not in columns:
            db.execute("ALTER TABLE jobs ADD COLUMN street TEXT NOT NULL DEFAULT ''")
        if "contact_tried_at" not in columns:
            # Wann zuletzt ohne Ergebnis nach Kontaktdaten gesucht wurde.
            db.execute(
                "ALTER TABLE jobs ADD COLUMN contact_tried_at TEXT NOT NULL DEFAULT ''"
            )
        if "contact_tried_for" not in columns:
            # Welche Angaben damals schon fehlten - dafuer nicht neu suchen.
            db.execute(
                "ALTER TABLE jobs ADD COLUMN contact_tried_for TEXT NOT NULL DEFAULT ''"
            )
        if "has_form" not in columns:
            # Bewerbungsformular auf der Seite des Arbeitgebers erkannt.
            db.execute(
                "ALTER TABLE jobs ADD COLUMN has_form INTEGER NOT NULL DEFAULT 0"
            )
        if "form_checked" not in columns:
            # 1 = Seite wurde geprueft; 0 = beim naechsten Lauf nachsehen.
            db.execute(
                "ALTER TABLE jobs ADD COLUMN form_checked INTEGER NOT NULL DEFAULT 0"
            )
        if "expiry_checked_at" not in columns:
            # Wann die Seite zuletzt auf «abgelaufen» geprueft wurde.
            db.execute(
                "ALTER TABLE jobs ADD COLUMN expiry_checked_at "
                "TEXT NOT NULL DEFAULT ''"
            )
        # Fuer Stellen ohne gefundenes Formular das Ergebnis der alten
        # Pruefung verwerfen, damit Formulare in eingebetteten Seiten und
        # hinter Bewerben-Verweisen nachtraeglich erkannt werden.
        known = db.execute(
            "SELECT value FROM meta WHERE key = 'form_check_version'"
        ).fetchone()
        if str(known["value"] if known else "") != FORM_CHECK_VERSION:
            db.execute("UPDATE jobs SET form_checked = 0 WHERE has_form = 0")
            db.execute(
                """
                INSERT INTO meta (key, value) VALUES ('form_check_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (FORM_CHECK_VERSION,),
            )
        app_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(applications)")
        }
        if "tracking" not in app_columns:
            db.execute(
                "ALTER TABLE applications ADD COLUMN tracking TEXT NOT NULL DEFAULT ''"
            )
        if "follow_up_sent_at" not in app_columns:
            db.execute(
                "ALTER TABLE applications ADD COLUMN follow_up_sent_at "
                "TEXT NOT NULL DEFAULT ''"
            )
        reply_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(replies)")
        }
        if "body" not in reply_columns:
            # Ganze Antwort speichern, damit sie sich im Fenster lesen laesst.
            db.execute("ALTER TABLE replies ADD COLUMN body TEXT NOT NULL DEFAULT ''")
        if "seen" not in reply_columns:
            db.execute("ALTER TABLE replies ADD COLUMN seen INTEGER NOT NULL DEFAULT 0")
        if "reply_kind" in app_columns:
            # Frueher blieb eine blosse Antwort ohne eigenen Status; der Filter
            # «Antwort» lief deshalb ins Leere. Alte Bewerbungen nachziehen.
            db.execute(
                "UPDATE applications SET status = 'info' "
                "WHERE reply_kind = 'info' "
                "AND status IN ('gesendet', 'nachgefasst')"
            )

    # ------------------------------------------------------------------
    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            yield connection
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
        return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Stellen
    # ------------------------------------------------------------------
    def upsert_job(self, job: Job, now: str = "") -> bool:
        """Neue Stelle eintragen; True, wenn sie noch nicht bekannt war."""
        row = job.to_row()
        stamp = now or ""
        with self._db() as db:
            existing = db.execute(
                "SELECT 1 FROM jobs WHERE id = ?", (row["id"],)
            ).fetchone()
            if existing is not None:
                # Bekannte Stelle: nur der letzte Sichtkontakt wird nachgefuehrt.
                # Adresse nachtragen: das Portal liefert sie erst spaeter oder
                # eine neue Fassung der Anzeige bringt sie mit.
                db.execute(
                    "UPDATE jobs SET last_seen = ?, published = ?, distance_km = ?, "
                    "street = CASE WHEN ? <> '' THEN ? ELSE street END, "
                    "zip = CASE WHEN ? <> '' THEN ? ELSE zip END, "
                    # Leere Angaben aus der neuen Portalantwort nachtragen;
                    # bereits gefuellte Felder bleiben unangetastet.
                    "title = CASE WHEN title = '' THEN ? ELSE title END, "
                    "company = CASE WHEN company = '' THEN ? ELSE company END, "
                    "city = CASE WHEN city = '' THEN ? ELSE city END, "
                    "contact_name = CASE WHEN contact_name = '' THEN ? "
                    "ELSE contact_name END, "
                    "contact_email = CASE WHEN contact_email = '' THEN ? "
                    "ELSE contact_email END WHERE id = ?",
                    (
                        stamp,
                        row["published"],
                        row["distance_km"],
                        row["street"],
                        row["street"],
                        row["zip"],
                        row["zip"],
                        row["title"],
                        row["company"],
                        row["city"],
                        row.get("contact_name") or "",
                        row.get("contact_email") or "",
                        row["id"],
                    ),
                )
                return False
            db.execute(
                """
                INSERT INTO jobs (
                    id, source, source_id, title, company, city, zip, street,
                    canton, workload, url, published, description, keywords,
                    distance_km, first_seen, last_seen, contact_email,
                    contact_name, raw
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["source"],
                    row["source_id"],
                    row["title"],
                    row["company"],
                    row["city"],
                    row["zip"],
                    row["street"],
                    row["canton"],
                    row["workload"],
                    row["url"],
                    row["published"],
                    row["description"],
                    row["keywords"],
                    row["distance_km"],
                    stamp,
                    stamp,
                    row.get("contact_email") or job.contact_address(),
                    row.get("contact_name") or "",
                    row["raw"],
                ),
            )
            return True

    def delete_job(self, job_id: str) -> bool:
        """Eine Stelle aus der Ablage entfernen (Anzeige abgelaufen)."""
        with self._db() as db:
            cursor = db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            removed = cursor.rowcount
        return removed > 0

    def jobs_for_expiry_check(self, limit: int = 15) -> list[dict[str, Any]]:
        """Stellen fuer die Ablaufpruefung, die aeltesten zuerst.

        Noch nie gepruefte kommen zuerst, danach die am laengsten nicht mehr
        geprueften; innerhalb dieser Reihenfolge zaehlt das Datum der Anzeige
        (aelteste zuerst). So kommt jede Zeile einmal dran, statt dass immer
        dieselben alten Anzeigen abgefragt werden.
        """
        with self._db() as db:
            return self._rows(
                db.execute(
                    """
                    SELECT * FROM jobs
                    WHERE status <> 'archiviert'
                    ORDER BY CASE WHEN expiry_checked_at = '' THEN 0 ELSE 1 END,
                             expiry_checked_at ASC,
                             COALESCE(NULLIF(published, ''), first_seen) ASC,
                             first_seen ASC
                    LIMIT ?
                    """,
                    (max(1, int(limit)),),
                )
            )

    def update_job(self, job_id: str, **fields: Any) -> None:
        changes = {key: value for key, value in fields.items() if key in JOB_FIELDS}
        if not changes:
            return
        assignments = ", ".join(f"{key} = ?" for key in changes)
        with self._db() as db:
            db.execute(
                f"UPDATE jobs SET {assignments} WHERE id = ?",
                (*changes.values(), job_id),
            )

    def set_job_analysis(
        self, job_id: str, score: int, template_id: str, keywords: list[str]
    ) -> None:
        import json

        self.update_job(
            job_id,
            score=int(score),
            template_id=template_id or "",
            keywords=json.dumps(keywords, ensure_ascii=False),
        )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list_jobs(
        self,
        status: str | None = None,
        search: str = "",
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM jobs"
        conditions: list[str] = []
        values: list[Any] = []
        if status:
            conditions.append("status = ?")
            values.append(status)
        if search.strip():
            conditions.append(
                "(title LIKE ? OR company LIKE ? OR city LIKE ? "
                "OR street LIKE ? OR zip LIKE ? OR keywords LIKE ?)"
            )
            needle = f"%{search.strip()}%"
            values.extend([needle] * 6)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY score DESC, published DESC, first_seen DESC LIMIT ?"
        values.append(limit)
        with self._db() as db:
            return self._rows(db.execute(query, values))

    def reclassify_general_jobs(self, template_id: str) -> int:
        """Stellen der Allgemeinen Vorlage aus «passend» herausziehen."""
        if not template_id:
            return 0
        with self._db() as db:
            cursor = db.execute(
                "UPDATE jobs SET status = 'allgemein' "
                "WHERE status = 'passend' AND template_id = ?",
                (template_id,),
            )
            return int(cursor.rowcount or 0)

    def job_counts(self) -> dict[str, int]:
        with self._db() as db:
            rows = self._rows(
                db.execute("SELECT status, COUNT(*) AS anzahl FROM jobs GROUP BY status")
            )
        return {row["status"]: int(row["anzahl"]) for row in rows}

    # ------------------------------------------------------------------
    # Bewerbungen
    # ------------------------------------------------------------------
    def add_application(
        self,
        job_id: str,
        template_id: str,
        subject: str,
        body: str,
        draft_id: str = "",
        conversation_id: str = "",
        web_link: str = "",
        status: str = "entwurf",
        created_at: str = "",
        tracking: str = "",
    ) -> int:
        with self._db() as db:
            cursor = db.execute(
                """
                INSERT INTO applications (
                    job_id, template_id, subject, body, draft_id, conversation_id,
                    web_link, status, created_at, tracking
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    template_id,
                    subject,
                    body,
                    draft_id,
                    conversation_id,
                    web_link,
                    status,
                    created_at,
                    tracking,
                ),
            )
            return int(cursor.lastrowid or 0)

    def update_application(self, app_id: int, **fields: Any) -> None:
        changes = {
            key: value for key, value in fields.items() if key in APPLICATION_FIELDS
        }
        if not changes:
            return
        assignments = ", ".join(f"{key} = ?" for key in changes)
        with self._db() as db:
            db.execute(
                f"UPDATE applications SET {assignments} WHERE id = ?",
                (*changes.values(), app_id),
            )

    def get_application(self, app_id: int) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute(
                """
                SELECT a.*, j.title, j.company, j.city, j.url, j.template_id AS job_template
                FROM applications a LEFT JOIN jobs j ON j.id = a.job_id
                WHERE a.id = ?
                """,
                (app_id,),
            ).fetchone()
        return dict(row) if row else None

    def application_by_tracking(self, tracking: str) -> dict[str, Any] | None:
        """Bewerbung anhand der in der Mail mitgereisten Kennung finden."""
        code = (tracking or "").strip()
        if not code:
            return None
        with self._db() as db:
            row = db.execute(
                """
                SELECT a.*, j.title, j.company, j.city, j.url
                FROM applications a LEFT JOIN jobs j ON j.id = a.job_id
                WHERE a.tracking = ? ORDER BY a.id DESC LIMIT 1
                """,
                (code,),
            ).fetchone()
        return dict(row) if row else None

    def application_by_job(self, job_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM applications WHERE job_id = ? ORDER BY id DESC LIMIT 1",
                (job_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_applications(
        self,
        status: str | None = None,
        limit: int = 500,
        *,
        statuses: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Bewerbungen auflisten - optional nach einem oder mehreren Stati."""
        query = """
            SELECT a.*, j.title, j.company, j.city, j.url
            FROM applications a LEFT JOIN jobs j ON j.id = a.job_id
        """
        values: list[Any] = []
        wanted = [item for item in (statuses or []) if item]
        if wanted:
            placeholders = ", ".join("?" for _ in wanted)
            query += f" WHERE a.status IN ({placeholders})"
            values.extend(wanted)
        elif status:
            query += " WHERE a.status = ?"
            values.append(status)
        query += " ORDER BY a.id DESC LIMIT ?"
        values.append(limit)
        with self._db() as db:
            return self._rows(db.execute(query, values))

    def application_counts(self) -> dict[str, int]:
        with self._db() as db:
            rows = self._rows(
                db.execute(
                    "SELECT status, COUNT(*) AS anzahl FROM applications GROUP BY status"
                )
            )
        return {row["status"]: int(row["anzahl"]) for row in rows}

    def active_applications(self) -> list[dict[str, Any]]:
        with self._db() as db:
            return self._rows(
                db.execute(
                    """
                    SELECT a.*, j.title, j.company, j.city, j.url
                    FROM applications a LEFT JOIN jobs j ON j.id = a.job_id
                    WHERE a.status IN ('gesendet', 'nachgefasst', 'einladung', 'info')
                    ORDER BY a.sent_at DESC
                    """
                )
            )

    def due_follow_ups(self, days: int = 14, reference: date | None = None) -> list[dict[str, Any]]:
        """Bewerbungen ohne Antwort, deren Nachfrist abgelaufen ist."""
        reference = reference or date.today()
        limit = reference - timedelta(days=max(1, int(days)))
        result = []
        for application in self.list_applications():
            if application.get("status") != "gesendet":
                continue
            if application.get("last_reply_at") or application.get("follow_up_at"):
                continue
            sent = parse_date(application.get("sent_at"))
            if sent is not None and sent <= limit:
                result.append(application)
        return result

    # ------------------------------------------------------------------
    # Antworten
    # ------------------------------------------------------------------
    def add_reply(
        self,
        application_id: int,
        message_id: str,
        received_at: str,
        sender: str,
        subject: str,
        kind: str,
        snippet: str,
        body: str = "",
    ) -> bool:
        with self._db() as db:
            cursor = db.execute(
                """
                INSERT OR IGNORE INTO replies (
                    application_id, message_id, received_at, sender, subject, kind,
                    snippet, body
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    application_id,
                    message_id,
                    received_at,
                    sender,
                    subject,
                    kind,
                    snippet,
                    body,
                ),
            )
            return cursor.rowcount > 0

    def unseen_by_application(self) -> dict[int, int]:
        """Anzahl noch nicht angesehener Antworten je Bewerbung."""
        with self._db() as db:
            rows = db.execute(
                "SELECT application_id, COUNT(*) AS number FROM replies "
                "WHERE seen = 0 GROUP BY application_id"
            ).fetchall()
        return {int(row["application_id"]): int(row["number"]) for row in rows}

    def unclassified_by_application(self) -> dict[int, int]:
        """Ungelesene Antworten ohne Zuordnung - nur die brauchen ein Blinken."""
        with self._db() as db:
            rows = db.execute(
                "SELECT application_id, COUNT(*) AS number FROM replies "
                "WHERE seen = 0 AND kind NOT IN ('zusage', 'einladung', 'absage') "
                "GROUP BY application_id"
            ).fetchall()
        return {int(row["application_id"]): int(row["number"]) for row in rows}

    def set_reply_kind(self, application_id: int, kind: str) -> bool:
        """Die neueste Antwort einer Bewerbung nachtraeglich einordnen."""
        with self._db() as db:
            cursor = db.execute(
                "UPDATE replies SET kind = ? WHERE id = ("
                "SELECT MAX(id) FROM replies WHERE application_id = ?)",
                (kind, application_id),
            )
            return cursor.rowcount > 0

    def unseen_total(self) -> int:
        """Alle noch nicht geöffneten Antworten - gelesene zählen nicht mit."""
        with self._db() as db:
            row = db.execute(
                "SELECT COUNT(*) AS number FROM replies WHERE seen = 0"
            ).fetchone()
        return int(row["number"]) if row is not None else 0

    def reply_counts(self) -> dict[int, int]:
        """Anzahl Antworten je Bewerbung (gesehen und ungelesen)."""
        with self._db() as db:
            rows = db.execute(
                "SELECT application_id, COUNT(*) AS number FROM replies "
                "GROUP BY application_id"
            ).fetchall()
        return {int(row["application_id"]): int(row["number"]) for row in rows}

    def mark_replies_seen(self, application_id: int) -> int:
        """Antworten einer Bewerbung als gelesen markieren."""
        with self._db() as db:
            cursor = db.execute(
                "UPDATE replies SET seen = 1 WHERE application_id = ? AND seen = 0",
                (application_id,),
            )
            return cursor.rowcount

    def replies_for(self, application_id: int) -> list[dict[str, Any]]:
        with self._db() as db:
            return self._rows(
                db.execute(
                    "SELECT * FROM replies WHERE application_id = ? ORDER BY id",
                    (application_id,),
                )
            )

    # ------------------------------------------------------------------
    # Protokoll und Zustand
    # ------------------------------------------------------------------
    def log(self, kind: str, message: str, at: str = "") -> None:
        with self._db() as db:
            db.execute(
                "INSERT INTO events (at, kind, message) VALUES (?, ?, ?)",
                (at, kind, message),
            )

    def events(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._db() as db:
            return self._rows(
                db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))
            )

    def meta_get(self, key: str, default: str = "") -> str:
        with self._db() as db:
            row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def meta_set(self, key: str, value: str) -> None:
        with self._db() as db:
            db.execute(
                """
                INSERT INTO meta (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
