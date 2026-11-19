"""Datenmodell der Stellenanzeigen."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .text import emails, parse_date


@dataclass
class Job:
    """Eine Stellenanzeige, wie sie in Datenbank und Oberflaeche gebraucht wird."""

    id: str
    source: str
    source_id: str
    title: str
    company: str
    city: str = ""
    zip: str = ""
    street: str = ""
    canton: str = ""
    workload: str = ""
    workload_min: int = 0
    workload_max: int = 0
    url: str = ""
    apply_url: str = ""
    contact_email: str = ""
    contact_name: str = ""
    published: str = ""
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    distance_km: float | None = None
    home_office: bool = False
    # Auf der Bewerbungsseite stehen Eingabe- und Upload-Felder.
    has_form: bool = False
    # Wurde die Bewerbungsseite schon auf ein Formular geprueft?
    form_checked: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    def keyword_text(self) -> str:
        return ", ".join(self.keywords)

    def haystack(self) -> str:
        """Alles, was fuer die Stichwortsuche zaehlt."""
        return " ".join(
            [
                self.title,
                self.company,
                self.description,
                self.keyword_text(),
                self.canton,
            ]
        )

    def published_date(self) -> str:
        parsed = parse_date(self.published)
        return parsed.isoformat() if parsed else ""

    def contact_address(self) -> str:
        """Erste Bewerbungsadresse - aus Kontaktblock oder Beschreibung."""
        if self.contact_email:
            return self.contact_email
        for candidate in emails(self.haystack()):
            return candidate
        return ""

    def domained(self) -> list[str]:
        """Domains, ueber die dieser Betrieb schreibt."""
        from .text import domain_of

        result: list[str] = []
        for candidate in emails(self.haystack()):
            value = domain_of(candidate)
            if value and value not in result:
                result.append(value)
        portfolio = self.raw.get("company") if isinstance(self.raw, dict) else None
        if isinstance(portfolio, dict):
            value = domain_of(str(portfolio.get("homepage") or ""))
            if value and value not in result:
                result.append(value)
        value = domain_of(self.apply_url)
        if value and value not in result:
            result.append(value)
        return result

    # ------------------------------------------------------------------
    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "source_id": self.source_id,
            "title": self.title,
            "company": self.company,
            "city": self.city,
            "zip": self.zip,
            "street": self.street,
            "canton": self.canton,
            "workload": self.workload,
            "url": self.url,
            "published": self.published_date(),
            "description": self.description,
            "contact_name": self.contact_name,
            "contact_email": self.contact_email,
            "keywords": json.dumps(self.keywords, ensure_ascii=False),
            "distance_km": self.distance_km,
            "has_form": int(self.has_form),
            "form_checked": int(self.form_checked),
            "raw": json.dumps(self.raw, ensure_ascii=False),
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Job":
        try:
            keywords = json.loads(row.get("keywords") or "[]")
        except ValueError:
            keywords = []
        try:
            raw = json.loads(row.get("raw") or "{}")
        except ValueError:
            raw = {}
        return cls(
            id=str(row.get("id") or ""),
            source=str(row.get("source") or ""),
            source_id=str(row.get("source_id") or ""),
            title=str(row.get("title") or ""),
            company=str(row.get("company") or ""),
            city=str(row.get("city") or ""),
            zip=str(row.get("zip") or ""),
            street=str(row.get("street") or ""),
            canton=str(row.get("canton") or ""),
            workload=str(row.get("workload") or ""),
            url=str(row.get("url") or ""),
            apply_url=str((raw or {}).get("urlApplication") or ""),
            contact_email=str(row.get("contact_email") or ""),
            contact_name=str(row.get("contact_name") or ""),
            published=str(row.get("published") or ""),
            description=str(row.get("description") or ""),
            keywords=[str(item) for item in keywords],
            distance_km=(
                float(row["distance_km"]) if row.get("distance_km") is not None else None
            ),
            home_office=bool((raw or {}).get("homeOffice")),
            has_form=bool(row.get("has_form")),
            form_checked=bool(row.get("form_checked")),
            raw=raw,
        )
