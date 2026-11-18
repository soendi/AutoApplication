from __future__ import annotations

from datetime import date, datetime, timezone

from autoapplication.core.config import Settings
from autoapplication.core.models import Job
from autoapplication.core.ostjob import (
    SearchQuery,
    build_url,
    job_matches,
    parse_vacancy,
    search_jobs,
    slugify,
    web_url,
    workload_overlaps,
)

ITEM = {
    "id": 1088366,
    "title": "Lehre Kaufmann/-frau Internationale <b class=\"hi\">Speditionslogistik</b>",
    "companyId": 1656,
    "workplaceZip": "9423",
    "workplaceCity": "Altenrhein",
    "activity": "<p>Disposition und <strong>Transport</strong></p>",
    "requirements": "<ul><li>Zoll</li></ul>",
    "offer": "",
    "contact": "<em>Ihr Kontakt</em><br />Frau Volek<br />nadia.volek@example.ch",
    "urlApplication": "https://example.ch/bewerbung",
    "dateFirstPublished": "2026-07-30T15:06:55.000+02:00",
    "dateActualization": "2026-11-06",
    "keywords": "Spedition, Transport, Kaufmann, Kauffrau, Lehre, Altenrhein",
    "typeKey": 3,
    "typeValueMin": 80,
    "typeValueMax": 100,
    "homeOffice": False,
    "coordinates": [{"ort": "Altenrhein", "latitude": 47.491185, "longitude": 9.555511}],
    "cantons": ["St. Gallen"],
    "company": {
        "name": "Gebrüder Weiss AG",
        "homepage": "https://www.gw-world.com/ch/",
        "city": "Altenrhein",
        "zip": "9423",
    },
}


def test_slug_and_web_url() -> None:
    assert slugify("Lehre Kaufmann/-frau Internationale Speditionslogistik") == (
        "lehre-kaufmann-frau-internationale-speditionslogistik"
    )
    assert web_url(1088366, "Lagermitarbeiter Logistik") == (
        "https://www.ostjob.ch/job/lagermitarbeiter-logistik/1088366"
    )
    assert web_url(42) == "https://www.ostjob.ch/job/42"


def test_build_url_contains_filters() -> None:
    query = SearchQuery(
        query="Spedition",
        place="Balgach 9436 (SG)",
        place_code="balgach-sg-9436",
        place_value="Balgach 9436 (SG)",
        radius_km=15,
        lat="47.4055",
        lng="9.6087",
        page=2,
        page_size=10,
        order="by_relevance",
    )
    url = build_url(query)
    assert "api.ostjob.ch/frontend/vacancy/search?" in url
    assert "search=Spedition" in url
    assert "placeCode=balgach-sg-9436" in url
    assert "radius=15" in url
    assert "page=2" in url
    assert "pageSize=10" in url
    assert "lat=47.4055" in url


def test_parse_vacancy_cleans_html_and_distance() -> None:
    job = parse_vacancy(ITEM, home=(47.4055, 9.6087))
    assert job.id == "ostjob:1088366"
    assert job.company == "Gebrüder Weiss AG"
    assert "<b" not in job.title
    assert "Speditionslogistik" in job.title
    assert job.workload == "80-100 %"
    assert job.canton == "St. Gallen"
    assert job.keywords[0] == "Spedition"
    assert "nadia.volek@example.ch" in job.contact_address()
    assert "gw-world.com" in job.domained()
    assert job.distance_km is not None and 0 < job.distance_km < 20
    assert job.published == "2026-07-30"
    assert job.apply_url.endswith("/bewerbung")
    assert "Zoll" in job.description
    assert "<li>" not in job.description


def test_parse_vacancy_without_coordinates() -> None:
    item = dict(ITEM)
    item.pop("coordinates")
    job = parse_vacancy(item)
    assert job.distance_km is None


def test_workload_overlap() -> None:
    job = Job(id="x", source="ostjob", source_id="1", title="t", company="c", workload_min=80, workload_max=100)
    assert workload_overlaps(job, 60, 100) is True
    assert workload_overlaps(job, 20, 40) is False
    assert workload_overlaps(job, 90, 90) is True
    unknown = Job(id="y", source="ostjob", source_id="2", title="t", company="c")
    assert workload_overlaps(unknown, 80, 100) is True


def _settings(tmp_path) -> Settings:
    settings = Settings(tmp_path / "e.json")
    settings.set("search.queries", ["Spedition"])
    settings.set("search.workload_min", 70)
    settings.set("search.workload_max", 100)
    settings.set("search.max_commute_km", 40)
    settings.set("search.max_age_days", 400)
    settings.set("search.exclude", "Lehre")
    return settings


def test_job_matches_exclusions(tmp_path) -> None:
    settings = _settings(tmp_path)
    job = parse_vacancy(ITEM, home=(47.4055, 9.6087))
    assert job_matches(job, settings, date(2026, 11, 18)) is False  # "Lehre" ausgeschlossen

    settings.set("search.exclude", "")
    assert job_matches(job, settings, date(2026, 11, 18)) is True

    settings.set("search.max_commute_km", 1)
    assert job_matches(job, settings, date(2026, 11, 18)) is False

    settings.set("search.max_commute_km", 40)
    settings.set("search.max_age_days", 5)
    assert job_matches(job, settings, date(2026, 11, 18)) is False

    settings.set("search.max_age_days", 400)
    settings.set("search.workload_min", 20)
    settings.set("search.workload_max", 40)
    assert job_matches(job, settings, date(2026, 11, 18)) is False


class FakeClient:
    def __init__(self, pages: dict[int, tuple[list[Job], int]]) -> None:
        self.pages = pages
        self.queries: list[SearchQuery] = []

    def vacancies(self, query: SearchQuery, home=None):
        self.queries.append(query)
        return self.pages.get(query.page, ([], 1))


def _job(identifier: str, title: str = "Speditionskaufmann") -> Job:
    return Job(
        id=f"ostjob:{identifier}",
        source="ostjob",
        source_id=identifier,
        title=title,
        company="Muster AG",
        city="Balgach",
        workload="80-100 %",
        workload_min=80,
        workload_max=100,
        published="2026-11-10",
        description="Disposition",
        keywords=["Spedition"],
    )


def test_search_jobs_pages_and_dedupe(tmp_path) -> None:
    settings = _settings(tmp_path)
    settings.set("search.exclude", "")
    settings.set("search.max_pages", 3)
    settings.set("search.queries", ["Spedition", "Logistik"])
    client = FakeClient(
        {
            1: ([_job("1"), _job("2")], 2),
            2: ([_job("2"), _job("3")], 2),
        }
    )
    jobs = search_jobs(
        settings, client=client, now=datetime(2026, 11, 18, tzinfo=timezone.utc)
    )
    assert [job.source_id for job in jobs] == ["1", "2", "3"]
    assert len(client.queries) == 4  # zwei Begriffe, je zwei Seiten
    assert client.queries[0].page == 1
    assert client.queries[1].page == 2
