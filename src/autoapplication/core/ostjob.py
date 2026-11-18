"""Stellen von ostjob.ch holen.

Die offizielle JSON-Schnittstelle des Portals ist erreichbar unter
``https://api.ostjob.ch/frontend/vacancy/search``. Sie verlangt die Herkunft
der Webseite (Origin/Referer), deshalb setzt der Client diese Kopfzeilen.
Gefiltert wird anschliessend im Programm: Pensum, Arbeitsweg, Kanton,
Ausschluss-Stichworte und Alter der Anzeige.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from .config import Settings
from .models import Job
from .text import (
    contact_person,
    emails,
    format_workload,
    haversine_km,
    normalize,
    parse_date,
    split_terms,
    strip_html,
)

log = logging.getLogger(__name__)

BASE = "https://api.ostjob.ch/frontend"
SEARCH_PATH = "/vacancy/search"
WEB_BASE = "https://www.ostjob.ch"
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Origin": WEB_BASE,
    "Referer": f"{WEB_BASE}/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
    ),
}


class OstjobError(RuntimeError):
    """Stellenabruf fehlgeschlagen - Meldung fuer die Oberflaeche."""


@dataclass
class SearchQuery:
    """Eine Suche an das Portal."""

    query: str
    place: str = ""
    place_code: str = ""
    place_value: str = ""
    radius_km: int = 25
    lat: str = ""
    lng: str = ""
    page: int = 1
    page_size: int = 25
    order: str = "by_relevance"

    def as_params(self) -> dict[str, str]:
        params: dict[str, str] = {
            "page": str(max(1, int(self.page))),
            "pageSize": str(max(1, min(100, int(self.page_size)))),
            "order": self.order or "by_relevance",
            "radius": str(max(0, int(self.radius_km))),
        }
        if self.query.strip():
            params["search"] = self.query.strip()
        if self.place.strip():
            params["place"] = self.place.strip()
            params["placeValue"] = (self.place_value or self.place).strip()
            if self.place_code.strip():
                params["placeCode"] = self.place_code.strip()
        if self.lat.strip() and self.lng.strip():
            params["lat"] = self.lat.strip()
            params["lng"] = self.lng.strip()
        return params


def build_url(query: SearchQuery, base: str = BASE) -> str:
    return f"{base}{SEARCH_PATH}?{urllib.parse.urlencode(query.as_params())}"


def slugify(value: str) -> str:
    """Titel in die Schreibweise der Portaladresse bringen."""
    text = normalize(value)
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    text = text.replace("ß", "ss")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:80]


def web_url(source_id: str | int, title: str = "") -> str:
    """Oeffentliche Adresse der Anzeige (Slug und Nummer wie im Portal)."""
    slug = slugify(title)
    if slug:
        return f"{WEB_BASE}/job/{slug}/{source_id}"
    return f"{WEB_BASE}/job/{source_id}"


def _as_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _first_coordinate(item: dict[str, Any]) -> tuple[float | None, float | None]:
    coordinates = item.get("coordinates") or []
    if isinstance(coordinates, list):
        for entry in coordinates:
            if not isinstance(entry, dict):
                continue
            try:
                return float(entry.get("latitude")), float(entry.get("longitude"))
            except (TypeError, ValueError):
                continue
    return None, None


def parse_vacancy(
    item: dict[str, Any],
    home: tuple[float, float] | None = None,
) -> Job:
    """Eine Anzeige aus der Portalantwort in ein Job-Objekt uebersetzen."""
    company = item.get("company") if isinstance(item.get("company"), dict) else {}
    company = company or {}
    source_id = str(item.get("id") or item.get("externalId") or "").strip()
    lat, lng = _first_coordinate(item)
    distance = None
    if home is not None and lat is not None and lng is not None:
        distance = haversine_km(home[0], home[1], lat, lng)

    parts = [
        strip_html(item.get("aiSummary")),
        strip_html(item.get("activity")),
        strip_html(item.get("requirements")),
        strip_html(item.get("offer")),
    ]
    description = "\n\n".join(part for part in parts if part).strip()
    if not description:
        description = strip_html(item.get("companyDescription"))

    cantons = item.get("cantons") or []
    canton = ", ".join(str(part) for part in cantons if part) if isinstance(cantons, list) else str(cantons)
    contact_block = "\n".join(
        strip_html(item.get(key))
        for key in ("contact", "applicationContact", "companyDescription")
        if item.get(key)
    )
    contact_email = ""
    for candidate in emails(contact_block):
        contact_email = candidate
        break

    published = (
        item.get("dateFirstPublished")
        or item.get("dateActualization")
        or item.get("updatedAt")
        or ""
    )
    parsed = parse_date(str(published))
    if parsed is None:
        parsed = date.today()
    title = strip_html(item.get("title")) or "Ohne Titel"

    return Job(
        id=f"ostjob:{source_id}",
        source="ostjob",
        source_id=source_id,
        title=title,
        company=str(company.get("name") or item.get("companyName") or "").strip(),
        city=str(item.get("workplaceCity") or company.get("city") or "").strip(),
        zip=str(item.get("workplaceZip") or company.get("zip") or "").strip(),
        canton=canton,
        workload=format_workload(item.get("typeValueMin"), item.get("typeValueMax")),
        workload_min=_as_int(item.get("typeValueMin")),
        workload_max=_as_int(item.get("typeValueMax")),
        url=web_url(source_id, title),
        apply_url=str(item.get("urlApplication") or "").strip(),
        contact_email=contact_email,
        contact_name=contact_person(contact_block),
        published=parsed.isoformat(),
        description=description,
        keywords=split_terms(item.get("keywords")),
        distance_km=distance,
        home_office=bool(item.get("homeOffice")),
        raw=item,
    )


class OstjobClient:
    """Duenner Client fuer die Portalsuche."""

    def __init__(
        self,
        timeout: float = 25.0,
        fetch: Callable[[str, float], bytes] | None = None,
    ) -> None:
        self.timeout = timeout
        self.fetch = fetch or _fetch_bytes

    def search(self, query: SearchQuery) -> dict[str, Any]:
        url = build_url(query)
        try:
            raw = self.fetch(url, self.timeout)
        except urllib.error.HTTPError as exc:
            raise OstjobError(f"ostjob.ch antwortet mit Fehler {exc.code}.") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise OstjobError(f"ostjob.ch ist nicht erreichbar: {exc}") from exc
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError as exc:
            raise OstjobError("ostjob.ch lieferte keine verwertbare Antwort.") from exc
        if not isinstance(payload, dict):
            raise OstjobError("ostjob.ch lieferte ein unerwartetes Format.")
        return payload

    def vacancies(
        self,
        query: SearchQuery,
        home: tuple[float, float] | None = None,
    ) -> tuple[list[Job], int]:
        payload = self.search(query)
        items = payload.get("items") or []
        jobs = [parse_vacancy(item, home) for item in items if isinstance(item, dict)]
        jobs = [job for job in jobs if job.source_id]
        try:
            total_pages = int(payload.get("pages") or 0)
        except (TypeError, ValueError):
            total_pages = 0
        return jobs, total_pages


def _fetch_bytes(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def home_coordinates(settings: Settings) -> tuple[float, float] | None:
    try:
        lat = float(settings.text("search.lat").replace(",", "."))
        lng = float(settings.text("search.lng").replace(",", "."))
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng


def queries_from_settings(settings: Settings) -> list[SearchQuery]:
    place, code, value = settings.place_params()
    radius = int(settings.number("search.radius_km", 25) or 0)
    page_size = int(settings.number("search.page_size", 25) or 25)
    order = settings.text("search.order", "by_relevance") or "by_relevance"
    lat = settings.text("search.lat")
    lng = settings.text("search.lng")
    terms = settings.search_terms() or [""]
    return [
        SearchQuery(
            query=term,
            place=place,
            place_code=code,
            place_value=value,
            radius_km=radius,
            lat=lat,
            lng=lng,
            page=1,
            page_size=page_size,
            order=order,
        )
        for term in terms
    ]


def workload_overlaps(job: Job, minimum: int, maximum: int) -> bool:
    """Passt das Pensum der Anzeige in den gewuenschten Bereich?"""
    if minimum <= 0 and maximum <= 0:
        return True
    low = job.workload_min or job.workload_max or 0
    high = job.workload_max or job.workload_min or 0
    if low == 0 and high == 0:
        return True  # Angabe fehlt - nicht aussortieren
    if low > high:
        low, high = high, low
    wanted_low = minimum if minimum > 0 else 0
    wanted_high = maximum if maximum > 0 else 100
    return high >= wanted_low and low <= wanted_high


def job_matches(
    job: Job,
    settings: Settings,
    reference: date | None = None,
) -> bool:
    """Alle harten Filter aus den Einstellungen auf eine Anzeige anwenden."""
    reference = reference or date.today()
    minimum = int(settings.number("search.workload_min", 0) or 0)
    maximum = int(settings.number("search.workload_max", 100) or 100)
    if not workload_overlaps(job, minimum, maximum):
        return False

    max_commute = settings.number("search.max_commute_km", 0)
    if max_commute > 0 and job.distance_km is not None:
        if job.distance_km > max_commute:
            return False

    cantons = [normalize(item) for item in settings.canton_filter()]
    if cantons and job.canton:
        if not any(normalize(canton) in job.canton.lower() for canton in cantons):
            return False

    haystack = normalize(job.haystack())
    for term in settings.excluded_terms():
        if normalize(term) in haystack:
            return False

    max_age = int(settings.number("search.max_age_days", 0) or 0)
    if max_age > 0:
        published = parse_date(job.published)
        if published is not None and published < reference - timedelta(days=max_age):
            return False
    return True


def search_jobs(
    settings: Settings,
    client: OstjobClient | None = None,
    now: datetime | None = None,
    *,
    max_queries: int | None = None,
) -> list[Job]:
    """Alle Suchbegriffe abarbeiten und harte Filter anwenden."""
    client = client or OstjobClient()
    moment = now or datetime.now(timezone.utc)
    reference = moment.date()
    home = home_coordinates(settings)
    max_pages = max(1, int(settings.number("search.max_pages", 1) or 1))
    queries = queries_from_settings(settings)
    if max_queries:
        queries = queries[:max_queries]

    seen: set[str] = set()
    result: list[Job] = []
    for base in queries:
        for page in range(1, max_pages + 1):
            query = replace(base, page=page)
            try:
                jobs, total_pages = client.vacancies(query, home)
            except OstjobError:
                if page == 1:
                    raise
                break
            for job in jobs:
                if job.id in seen:
                    continue
                seen.add(job.id)
                if job_matches(job, settings, reference):
                    result.append(job)
            if total_pages and page >= total_pages:
                break
    # Neueste zuerst; bei gleichem Datum bleibt die Reihenfolge des Portals.
    result.sort(key=lambda item: item.published or "", reverse=True)
    log.info("ostjob: %d Stellen nach dem Filtern", len(result))
    return result
