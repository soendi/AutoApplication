"""Einstellungen und Ablageorte von AutoApplication.

Alles liegt im Benutzerordner ``AutoApplication`` - unter Windows
``%USERPROFILE%\\AutoApplication``, unter Linux und macOS ``~/AutoApplication``.
Fuer Tests laesst sich der Ordner ueber ``AUTOAPPLICATION_HOME`` umlenken.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

APP_DIR_NAME = "AutoApplication"

DEFAULTS: dict[str, Any] = {
    "profile": {
        "vorname": "",
        "nachname": "",
        "strasse": "",
        "plz": "",
        "wohnort": "",
        "telefon": "",
        "email": "",
        "erfahrung_jahre": "acht",
        "verfuegbar": "sofort",
        "interessen": [],
        "faehigkeiten": [],
    },
    "search": {
        "api_enabled": False,
        "queries": ["Spedition", "Logistik"],
        "place": "",
        "place_code": "",
        "place_value": "",
        "lat": "",
        "lng": "",
        "radius_km": 25,
        "max_commute_km": 45,
        "workload_min": 60,
        "workload_max": 100,
        "cantons": "",
        "exclude": "Lehre, Lehrstelle, Praktikum, Schnupperlehre",
        "order": "by_relevance",
        "page_size": 25,
        "max_pages": 3,
        "max_age_days": 45,
    },
    "matching": {
        "min_score": 2,
        "auto_draft": True,
        "max_drafts_per_run": 5,
    },
    "ai": {
        "enabled": False,
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_key": "",
        "timeout": 45,
    },
    "mail": {
        "provider": "outlook",
    },
    "outlook": {
        "enabled": False,
        "client_id": "",
        "tenant": "common",
        "account": "",
    },
    "google": {
        "client_id": "",
        "client_secret": "",
        "account": "",
    },
    "documents": {
        "folder": "",
        "attach": True,
        "cover_letter": True,
        "max_mb": 20,
    },
    "automation": {
        "daily_time": "07:30",
        "auto_on_start": True,
        "check_replies": True,
        "follow_up_days": 14,
        "notify_desktop": True,
    },
}


def app_home() -> Path:
    """Ordner fuer Einstellungen, Datenbank und Vorlagen."""
    override = os.environ.get("AUTOAPPLICATION_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / APP_DIR_NAME


def config_path() -> Path:
    return app_home() / "einstellungen.json"


def database_path() -> Path:
    return app_home() / "daten.db"


def templates_path() -> Path:
    return app_home() / "vorlagen.json"


def token_path() -> Path:
    return app_home() / "outlook_token.json"


def google_token_path() -> Path:
    return app_home() / "google_token.json"


def log_path() -> Path:
    return app_home() / "autoapplication.log"


def state_path() -> Path:
    return app_home() / "zustand.json"


def _merge(base: dict[str, Any], loaded: Any) -> dict[str, Any]:
    """Standardwerte mit gespeicherten Werten zusammenfuehren."""
    result = copy.deepcopy(base)
    if not isinstance(loaded, dict):
        return result
    for key, value in loaded.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


class Settings:
    """Einstellungen als verschachteltes Woerterbuch mit Punktschreibweise."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else config_path()
        self.data: dict[str, Any] = copy.deepcopy(DEFAULTS)

    # ------------------------------------------------------------------
    def load(self) -> "Settings":
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError:
            return self
        try:
            loaded = json.loads(raw)
        except ValueError:
            return self
        self.data = _merge(DEFAULTS, loaded)
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(self.path)

    # ------------------------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self.data
        for part in parts[:-1]:
            if not isinstance(node.get(part), dict):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = value

    def text(self, dotted: str, default: str = "") -> str:
        value = self.get(dotted, default)
        return "" if value is None else str(value)

    def number(self, dotted: str, default: float = 0) -> float:
        value = self.get(dotted, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def flag(self, dotted: str, default: bool = False) -> bool:
        value = self.get(dotted, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "ja", "true", "an", "yes"}

    # ------------------------------------------------------------------
    def ai_key(self) -> str:
        """Schluessel aus den Einstellungen, sonst aus der Umgebung."""
        stored = self.text("ai.api_key").strip()
        if stored:
            return stored
        names = ["AUTOAPPLICATION_AI_KEY"]
        if self.text("ai.provider", "openai").strip().lower() == "groq":
            names += ["GROQ_API_KEY", "OPENAI_API_KEY"]
        else:
            names += ["OPENAI_API_KEY", "GROQ_API_KEY"]
        for name in names:
            value = os.environ.get(name, "").strip()
            if value:
                return value
        return ""

    def profile(self) -> dict[str, str]:
        profile = self.get("profile", {})
        result: dict[str, str] = {}
        for key, value in profile.items():
            if isinstance(value, list):
                result[key] = ", ".join(str(item) for item in value)
            else:
                result[key] = str(value or "")
        for key in ("interessen", "faehigkeiten"):
            result[key] = ", ".join(self._terms(f"profile.{key}"))
        return result

    def search_terms(self) -> list[str]:
        value = self.get("search.queries", [])
        if isinstance(value, str):
            value = [value]
        terms = []
        for item in value or []:
            text = str(item).strip()
            if text:
                terms.append(text)
        return terms

    def excluded_terms(self) -> list[str]:
        raw = str(self.get("search.exclude", "") or "")
        return [part.strip() for part in raw.split(",") if part.strip()]

    def canton_filter(self) -> list[str]:
        raw = self.get("search.cantons", "")
        if isinstance(raw, list):
            raw = ",".join(str(item) for item in raw)
        return [part.strip() for part in str(raw).split(",") if part.strip()]

    def place_params(self) -> tuple[str, str, str]:
        place = self.text("search.place")
        code = self.text("search.place_code")
        value = self.text("search.place_value") or place
        return place, code, value

    def _terms(self, dotted: str) -> list[str]:
        """Stichwortliste aus Einstellungen lesen - Liste oder Freitext."""
        value = self.get(dotted, [])
        if isinstance(value, str):
            parts = value.replace(";", ",").splitlines()
            entries: list[str] = []
            for line in parts:
                entries.extend(line.split(","))
            return [entry.strip() for entry in entries if entry.strip()]
        return [str(entry).strip() for entry in value or [] if str(entry).strip()]

    def interests(self) -> list[str]:
        """Interessen in Stichworten - unabhaengig von den Faehigkeiten."""
        return self._terms("profile.interessen")

    def skills(self) -> list[str]:
        """Faehigkeiten in Stichworten."""
        return self._terms("profile.faehigkeiten")

    def mail_provider(self) -> str:
        """Welche E-Mail-Anbindung genutzt wird: outlook, google oder none."""
        provider = self.text("mail.provider", "outlook").strip().lower()
        return provider if provider in {"outlook", "google", "none"} else "outlook"


def ensure_home() -> Path:
    """Benutzerordner anlegen und zurueckgeben."""
    home = app_home()
    home.mkdir(parents=True, exist_ok=True)
    return home


def is_windows() -> bool:
    return sys.platform.startswith("win")
