"""Persoenliche Passung einer Stelle: Interessen und Faehigkeiten.

Die Vorlagenpassung sagt, ob eine Stelle zur bisherigen Richtung passt. Hier
kommt die persoenliche Sicht dazu: Was interessiert mich, und was kann ich
schon? Die Interessen wiegen bei der Auswahl mehr - gerade beim Branchenwechsel.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .text import normalize

# Verwandte Begriffe: Ein Stichwort im Profil trifft auch die anderen Woerter
# seiner Gruppe. So genuegen wenige Stichworte, statt jede Schreibweise
# einzeln aufzuzaehlen. Kurze Woerter unter drei Zeichen sind bewusst nicht
# als Suchwort enthalten - sie wuerden fast jede Anzeige treffen.
SYNONYMS: tuple[tuple[str, ...], ...] = (
    (
        "lager",
        "lagerung",
        "lagerhaltung",
        "lagerlogistik",
        "lagerist",
        "lagerarbeiter",
        "lagermitarbeiter",
        "lagerbewirtschaftung",
        "warenannahme",
        "wareneingang",
        "warenausgang",
        "kommissionierung",
        "kommissionieren",
        "picking",
        "magazin",
    ),
    (
        "logistik",
        "logistiker",
        "spedition",
        "speditionslogistik",
        "transport",
        "transportlogistik",
        "disposition",
        "transportdisposition",
        "fracht",
        "versand",
        "warenfluss",
        "supply chain",
        "lieferkette",
    ),
    (
        "spedition",
        "speditionskaufmann",
        "speditionssachbearbeiter",
        "speditionskoordination",
        "stückgut",
        "sammelgut",
        "luftfracht",
        "seefracht",
        "disposition",
        "fracht",
        "versand",
        "transport",
    ),
    (
        "export",
        "exportabwicklung",
        "exportsachbearbeiter",
        "ausfuhr",
        "aussenhandel",
        "aussenwirtschaft",
        "versandabwicklung",
        "handelsdokumente",
        "akkreditiv",
        "letter of credit",
    ),
    (
        "zoll",
        "zolldeklaration",
        "zollanmeldung",
        "zollsachbearbeiter",
        "exportkontrolle",
        "ursprungsnachweis",
        "präferenznachweis",
        "transit",
        "frachtpapiere",
    ),
    (
        "büro",
        "büroassistenz",
        "büroorganisation",
        "administration",
        "verwaltung",
        "sachbearbeitung",
        "sekretariat",
        "backoffice",
        "assistenz",
        "korrespondenz",
    ),
    (
        "empfang",
        "rezeption",
        "front office",
        "besucherempfang",
        "telefondienst",
        "telefon",
        "sekretariat",
        "büroorganisation",
    ),
    (
        "kundenkontakt",
        "kundenberatung",
        "kundenbetreuung",
        "kundenberater",
        "kundenservice",
        "kundenanfragen",
        "kundenpflege",
        "kundenzufriedenheit",
        "beratung",
        "verkaufsinnendienst",
        "callcenter",
        "call center",
        "reklamation",
    ),
    (
        "verkauf",
        "verkäufer",
        "verkaufsinnendienst",
        "verkaufsberater",
        "kundenberatung",
        "auftragsbearbeitung",
        "auftragsabwicklung",
        "offerte",
        "offertwesen",
        "detailhandel",
        "kundenkontakt",
        "beratung",
    ),
    (
        "informatik",
        "it-support",
        "it-administration",
        "helpdesk",
        "user help desk",
        "first level",
        "second level",
        "support",
        "ticketsystem",
        "anwenderbetreuung",
        "systemadministration",
        "edv",
        "software",
        "hardware",
        "netzwerk",
        "digitalisierung",
    ),
    (
        "technik",
        "techniker",
        "technisch",
        "systemtechnik",
        "servicetechniker",
        "service-techniker",
        "kundendienst",
        "service",
        "wartung",
        "reparatur",
        "instandhaltung",
        "störungsbehebung",
        "installation",
        "inbetriebnahme",
        "fernwartung",
        "peripherie",
        "schnittstellen",
    ),
    (
        "kassensystem",
        "kassensysteme",
        "kassensoftware",
        "kasse",
        "point of sale",
        "zahlungsterminal",
    ),
    (
        "produktion",
        "produktionsmitarbeiter",
        "fertigung",
        "herstellung",
        "serienfertigung",
        "einzelfertigung",
        "auftragsfertigung",
        "fliessband",
        "werkstatt",
        "montage",
    ),
    (
        "montage",
        "monteur",
        "montagemitarbeiter",
        "montieren",
        "zusammenbau",
        "baugruppen",
        "anlagenbau",
        "demontage",
        "mechanische montage",
    ),
    (
        "maschinenbedienung",
        "maschinenbediener",
        "anlagenbediener",
        "anlagenbedienung",
        "maschinenführer",
        "produktionsanlage",
        "anlage",
        "maschine",
        "einrichten",
        "rüsten",
        "prozessüberwachung",
    ),
    (
        "qualität",
        "qualitätssicherung",
        "qualitätskontrolle",
        "qualitätsprüfung",
        "qualitätsmanagement",
        "endkontrolle",
        "eingangskontrolle",
        "messmittel",
        "prüfprotokoll",
        "prüfung",
        "kontrolle",
    ),
    (
        "einkauf",
        "einkäufer",
        "beschaffung",
        "beschaffungswesen",
        "lieferant",
        "lieferanten",
        "bestellung",
        "bestellwesen",
        "offertvergleich",
        "materialwirtschaft",
        "konditionen",
        "verhandlung",
    ),
    (
        "buchhaltung",
        "buchhalter",
        "rechnungswesen",
        "finanzbuchhaltung",
        "finanzen",
        "debitoren",
        "kreditoren",
        "rechnungen",
        "zahlungsverkehr",
        "belege",
        "jahresabschluss",
        "lohnbuchhaltung",
        "mwst",
    ),
    (
        "personal",
        "personalwesen",
        "personaladministration",
        "human resources",
        "rekrutierung",
        "personaldossier",
        "lohnadministration",
        "bewerbermanagement",
        "personalentwicklung",
    ),
    (
        "sicherheit",
        "sicherheitsdienst",
        "sicherheitsmitarbeiter",
        "pforte",
        "pfortendienst",
        "wachdienst",
        "überwachung",
        "zutrittskontrolle",
        "ordnungsdienst",
    ),
    (
        "reinigung",
        "reinigungskraft",
        "unterhaltsreinigung",
        "gebäudereinigung",
        "grundreinigung",
        "fensterreinigung",
        "hausdienst",
        "hauswart",
        "putz",
        "hygiene",
    ),
    (
        "gastronomie",
        "restaurant",
        "gastgewerbe",
        "servicemitarbeiter",
        "kellner",
        "küche",
        "küchenhilfe",
        "bankett",
        "café",
        "bistro",
        "verpflegung",
        "gastgeber",
    ),
    (
        "hotel",
        "hotellerie",
        "rezeption",
        "housekeeping",
        "beherbergung",
        "reservation",
        "concierge",
        "etage",
    ),
    (
        "landwirtschaft",
        "landwirt",
        "gartenbau",
        "gärtner",
        "garten",
        "pflanzen",
        "tierpflege",
        "ernte",
        "grünpflege",
        "natur",
    ),
    (
        "pflege",
        "pflegehelfer",
        "pflegeassistenz",
        "betreuung",
        "senioren",
        "altersheim",
        "spital",
        "klinik",
        "arztpraxis",
        "praxisassistenz",
        "patienten",
        "gesundheit",
    ),
    (
        "sozial",
        "sozialbegleitung",
        "betreuung",
        "begleitung",
        "integration",
        "kinder",
        "jugend",
        "behinderung",
        "wohnheim",
        "alltagsbegleitung",
    ),
    (
        "bildung",
        "schule",
        "schulassistenz",
        "lernbegleitung",
        "nachhilfe",
        "unterricht",
        "kursleitung",
        "erwachsenenbildung",
    ),
    (
        "ausbildung",
        "lehrstelle",
        "lehrling",
        "lernende",
        "lernender",
        "berufslehre",
        "berufsbildung",
        "ausbildungsplatz",
        "schnupperlehre",
        "umschulung",
        "quereinstieg",
    ),
    (
        "marketing",
        "kommunikation",
        "social media",
        "werbung",
        "content",
        "öffentlichkeitsarbeit",
        "kampagne",
        "newsletter",
        "medien",
        "website",
    ),
    (
        "sap",
        "erp",
        "infor",
        "navision",
        "warenwirtschaft",
        "cloud suite",
    ),
    (
        "office",
        "word",
        "excel",
        "outlook",
        "powerpoint",
        "microsoft 365",
        "tabellen",
    ),
    (
        "stapler",
        "gabelstapler",
        "flurförderzeug",
        "staplerschein",
        "hubwagen",
    ),
    (
        "chauffeur",
        "fahrer",
        "kurier",
        "lieferfahrer",
        "fahrdienst",
        "zustellung",
        "auslieferung",
        "lieferdienst",
        "touren",
        "berufschauffeur",
        "führerausweis",
        "fahrausweis",
    ),
    (
        "handwerk",
        "handwerker",
        "gebäudetechnik",
        "instandhaltung",
        "reparatur",
        "sanitär",
        "elektro",
        "heizung",
        "lüftung",
        "hauswart",
        "facility",
        "werkzeug",
    ),
    (
        "baustelle",
        "bauarbeiter",
        "bauhauptgewerbe",
        "baunebengewerbe",
        "tiefbau",
        "hochbau",
        "ausbau",
        "maurer",
        "betonbau",
        "schalung",
        "gerüstbau",
    ),
    (
        "team",
        "teamarbeit",
        "teamfähig",
        "teamfähigkeit",
        "zusammenarbeit",
    ),
    (
        "selbstständig",
        "selbständig",
        "eigenverantwortlich",
        "eigeninitiative",
    ),
    (
        "zuverlässig",
        "zuverlässigkeit",
        "verlässlich",
        "gewissenhaft",
    ),
    (
        "flexibel",
        "flexibilität",
        "belastbar",
        "belastbarkeit",
    ),
    (
        "organisation",
        "organisieren",
        "organisiert",
        "planung",
        "koordination",
    ),
    (
        "englisch",
        "english",
        "englischkenntnisse",
    ),
    (
        "französisch",
        "francais",
        "französischkenntnisse",
    ),
)

# Kurze Stichworte, die als Suchwort fast jede Anzeige treffen wuerden. Sie
# fuehren nur ueber ihre Gruppe zu sinnvollen Treffern.
ALIASES = {
    "it": "informatik",
    "edv": "informatik",
    "hr": "personal",
    "pos": "kassensystem",
    "qs": "qualität",
    "bau": "baustelle",
}


def _build_variants() -> dict[str, tuple[str, ...]]:
    groups: dict[str, set[str]] = {}
    for group in SYNONYMS:
        words = {
            normalize(word) for word in group if len(normalize(word)) >= 3
        }
        for word in group:
            key = normalize(word)
            if key:
                groups.setdefault(key, set()).update(words)
    return {key: tuple(sorted(words)) for key, words in groups.items()}


_SYNONYM_VARIANTS = _build_variants()


def term_variants(term: str) -> tuple[str, ...]:
    """Suchwoerter zu einem Stichwort: es selbst und seine Verwandten."""
    key = normalize(term)
    key = ALIASES.get(key, key)
    variants = _SYNONYM_VARIANTS.get(key)
    return variants or (normalize(term),)


def job_text(job: dict[str, Any]) -> str:
    """Alles, was fuer den Vergleich mit Interessen und Faehigkeiten zaehlt."""
    return " ".join(
        str(job.get(key) or "")
        for key in ("title", "company", "city", "description", "keywords")
    )


def matching_terms(text: str, terms: Iterable[str]) -> list[str]:
    """Welche der Stichworte kommen im Text vor - auch als Verwandte?"""
    haystack = normalize(text)
    found: list[str] = []
    for term in terms:
        if any(variant in haystack for variant in term_variants(term)):
            found.append(term)
    return found


def personal_match(
    job: dict[str, Any],
    interests: Iterable[str],
    skills: Iterable[str],
) -> tuple[list[str], list[str]]:
    """Treffer bei den Interessen und bei den Faehigkeiten."""
    text = job_text(job)
    return matching_terms(text, interests), matching_terms(text, skills)


# Interessen wiegen mehr als Faehigkeiten - gerade beim Branchenwechsel.
INTEREST_WEIGHT = 0.6
SKILL_WEIGHT = 0.4


def personal_fit(
    job: dict[str, Any],
    interests: Iterable[str],
    skills: Iterable[str],
) -> int | None:
    """Anteil der Profil-Stichworte in der Anzeige, in Prozent (0 bis 100).

    Interessen zaehlen 60 %, Faehigkeiten 40 %. Ist nur eine der beiden Listen
    gefuellt, zaehlt sie allein. 100 % heisst: Alles kommt vor. Ohne Stichworte
    im Profil gibt es keinen Wert (``None``) - 0 % waere dort eine falsche
    Aussage.
    """
    interests = list(interests)
    skills = list(skills)
    found_interests, found_skills = personal_match(job, interests, skills)
    shares: list[tuple[float, float]] = []
    if interests:
        shares.append(
            (INTEREST_WEIGHT, len(found_interests) / len(interests))
        )
    if skills:
        shares.append((SKILL_WEIGHT, len(found_skills) / len(skills)))
    if not shares:
        return None
    weight = sum(share for share, _ in shares)
    value = sum(share * hit for share, hit in shares) / weight
    return round(100 * value)


def priority_key(
    interests: list[str],
    skills: list[str],
    score: int,
    published: str = "",
) -> tuple[int, int, int, str]:
    """Sortierschluessel: Interessen vor Faehigkeiten, dann die Passung."""
    return (len(interests), len(skills), int(score or 0), published or "")
