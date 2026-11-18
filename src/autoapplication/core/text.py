"""Kleine Text- und Rechenhelfer fuer AutoApplication."""

from __future__ import annotations

import html
import math
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

_TAG_RE = re.compile(r"<[^>]+>")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_OBFUSCATED_AT = re.compile(r"\s*[\[\(\{]\s*(?:at|ät)\s*[\]\)\}]\s*", re.IGNORECASE)
_OBFUSCATED_DOT = re.compile(
    r"\s*[\[\(\{]\s*(?:dot|punkt)\s*[\]\)\}]\s*", re.IGNORECASE
)
_CONTACT_RE = re.compile(
    r"\b(Herr|Herrn|Frau)\s+("
    r"(?:[A-ZÄÖÜ][a-zäöüß]{1,4}\.\s+)*"  # Titel wie "Dr. "
    r"[A-ZÄÖÜ][a-zäöüß\-]+(?:\s+[A-ZÄÖÜ][a-zäöüß\-]+)?"
    r")"
)
_CONTACT_TITLES = {
    "dr", "prof", "dipl", "med", "phil", "ing", "lic", "hans",
}
_CONTACT_STOP = {
    "und", "oder", "von", "vom", "in", "im", "der", "die", "das", "den",
    "bei", "mit", "für", "fuer", "als", "ihr", "ihre",
}
_SPACE_RE = re.compile(r"[ \t\u00a0]+")
_WORD_RE = re.compile(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß0-9\-+/.]{1,}")


def strip_html(value: str | None) -> str:
    """HTML aus dem Stellenportal in lesbaren Text verwandeln."""
    if not value:
        return ""
    text = re.sub(r"(?i)<br\s*/?>", "\n", str(value))
    text = re.sub(r"(?i)<li[^>]*>", "- ", text)
    text = re.sub(r"(?i)</(p|li|div|tr|h[1-6]|ul|ol)>", "\n", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _SPACE_RE.sub(" ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize(value: str | None) -> str:
    """Vergleichsform: klein geschrieben, einfache Leerzeichen."""
    if not value:
        return ""
    text = str(value).lower().replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def has_term(haystack: str, term: str) -> bool:
    """Steckt term im Text? Auch in Zusammensetzungen (Speditionslogistik)."""
    needle = normalize(term)
    if not needle:
        return False
    return needle in normalize(haystack)


def words(value: str | None) -> list[str]:
    return _WORD_RE.findall(value or "")


def split_terms(value: str | None, separator: str = ",") -> list[str]:
    """Stichworte aus einer Zeile wie "Spedition, Transport" lesen."""
    if not value:
        return []
    parts = re.split(r"[\n" + re.escape(separator) + r"]", str(value))
    return [part.strip() for part in parts if part.strip() and part.strip() not in {"-"}]


def emails(value: str | None) -> list[str]:
    text = deobfuscate(html.unescape(str(value or "")))
    return _EMAIL_RE.findall(text)


def domain_of(value: str | None) -> str:
    """Domain aus Adresse, Mail oder Link - ohne www und in Kleinschreibung."""
    text = (value or "").strip()
    if not text:
        return ""
    if "@" in text and "://" not in text:
        text = text.rsplit("@", 1)[-1]
    else:
        parsed = urlparse(text if "://" in text else f"https://{text}")
        text = parsed.hostname or ""
    text = text.lower().strip(".")
    return text[4:] if text.startswith("www.") else text


def haversine_km(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float | None:
    """Luftlinie zwischen zwei Punkten in Kilometern."""
    try:
        lat1, lon1, lat2, lon2 = (float(v) for v in (lat1, lon1, lat2, lon2))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90):
        return None
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return round(2 * radius * math.asin(math.sqrt(a)), 1)


def parse_date(value: str | None) -> date | None:
    """Datum aus ISO-, Portal- oder deutschem Format lesen."""
    text = (value or "").strip()
    if not text:
        return None
    candidates = [text.replace("Z", "+00:00")]
    if text.endswith("+0200") or text.endswith("+0100"):
        candidates.append(f"{text[:-5]}{text[-5:-2]}:{text[-2:]}")
    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            continue
    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], pattern).date()
        except ValueError:
            continue
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today() -> date:
    return date.today()


def format_date(value: str | None) -> str:
    parsed = parse_date(value)
    return parsed.strftime("%d.%m.%Y") if parsed else ""


def days_since(value: str | None, reference: date | None = None) -> int | None:
    parsed = parse_date(value)
    if parsed is None:
        return None
    reference = reference or date.today()
    return (reference - parsed).days


def format_workload(minimum: int | float | None, maximum: int | float | None) -> str:
    """Pensum als "80-100 %" darstellen."""
    try:
        low = int(minimum or 0)
        high = int(maximum or 0)
    except (TypeError, ValueError):
        return ""
    if low <= 0 and high <= 0:
        return ""
    if low <= 0:
        low = high
    if high <= 0:
        high = low
    if low == high:
        return f"{low} %"
    if low > high:
        low, high = high, low
    return f"{low}-{high} %"


def deobfuscate(value: str | None) -> str:
    """Verschleierte Adressen lesbar machen: "personal [at] firma [dot] ch"."""
    text = str(value or "")
    if not any(marker in text for marker in ("[", "(", "{")):
        return text
    text = _OBFUSCATED_AT.sub("@", text)
    text = _OBFUSCATED_DOT.sub(".", text)
    return text


def contact_person(value: str | None) -> str:
    """Ansprechperson aus der Anzeige: "Herr Müller" oder "Frau Meier".

    Ohne klares ``Herr``/``Frau`` bleibt das Ergebnis leer - geraten wird
    nicht, damit keine falsche Anrede entsteht.
    """
    text = strip_html(value)
    if not text:
        return ""
    for match in _CONTACT_RE.finditer(text):
        tokens = [
            token
            for token in match.group(2).split()
            if token.lower() not in _CONTACT_STOP
            and token.lower().rstrip(".") not in _CONTACT_TITLES
        ]
        if not tokens:
            continue
        # Bei "Hans Müller" ist das letzte Wort der Nachname.
        name = tokens[-1] if len(tokens) > 1 else tokens[0]
        title = "Herr" if match.group(1).lower() == "herrn" else match.group(1)
        return f"{title} {name}"
    return ""


def salutation(contact: str | None) -> str:
    """Anrede aus "Herr Müller"/"Frau Meier"; sonst allgemein."""
    text = (contact or "").strip()
    lowered = text.lower()
    if lowered.startswith("herr "):
        return f"Sehr geehrter {text}"
    if lowered.startswith("frau "):
        return f"Sehr geehrte {text}"
    return "Sehr geehrte Damen und Herren"


def short(value: str | None, length: int = 120) -> str:
    text = re.sub(r"\s+", " ", strip_html(value))
    if len(text) <= length:
        return text
    return text[: length - 1].rstrip() + "…"


def days_until(value: str | None, reference: date | None = None) -> int | None:
    parsed = parse_date(value)
    if parsed is None:
        return None
    reference = reference or date.today()
    return (parsed - reference).days


def plus_days(value: datetime | date | None, days: int) -> str:
    base = value or datetime.now(timezone.utc)
    if isinstance(base, datetime):
        base = base.date()
    return (base + timedelta(days=days)).isoformat()


# ----------------------------------------------------------------------
# Stellenanzeigen aufraeumen: Gendermarken, IDs und weibliche Formen
# ----------------------------------------------------------------------
_GENDER_MARKER = re.compile(
    r"[\s,\-–/]*[\(\[]\s*"
    r"(?:m\s*[/|]\s*w(?:\s*[/|]\s*[dxf])?"
    r"|w\s*[/|]\s*m(?:\s*[/|]\s*[dxf])?"
    r"|m\s*[/|]\s*f\s*[/|]\s*[dx]"
    r"|gn\*?|all\s+genders?|any\s+gender|divers|mixed)"
    r"\s*[\)\]]",
    re.IGNORECASE,
)
_GENDER_BARE = re.compile(
    r"\b(?:m\s*/\s*w\s*/\s*d|w\s*/\s*m\s*/\s*d|m\s*/\s*f\s*/\s*d"
    r"|m\s*/\s*w\s*/\s*x|gn\*?)\b",
    re.IGNORECASE,
)
_GENDER_SUFFIX = re.compile(r"(?<=[A-Za-zÄÖÜäöüß])(?:\*|:|_|·)\s*in\b", re.IGNORECASE)
_ID_REFERENCE = re.compile(
    r"(?i)\b(?:job-?id|stellen?-?(?:id|nummer)|inserat(?:s)?-?(?:id|nummer)"
    r"|referenz(?:-?nummer)?|ref(?:erenz)?\.?\s*(?:nr\.?|nummer)?)"
    r"\s*[:#]?\s*[A-Za-z0-9][A-Za-z0-9\-_/]{2,}"
)
_PAREN_NUMBER = re.compile(r"\(\s*(?:id\s*[:#]?\s*)?\d{4,}\s*\)", re.IGNORECASE)
_PAREN_CODE = re.compile(r"\(\s*\d{2,4}\s*[-/]\s*\d{3,}\s*\)")
_HASH_NUMBER = re.compile(r"(?<!\w)#\d{4,}\b")

_MASCULINE_WORDS = {
    "Köchin": "Koch",
    "Ärztin": "Arzt",
    "Anwältin": "Anwalt",
    "Krankenschwester": "Krankenpfleger",
    "Hebamme": "Hebamme",
    "Kauffrau": "Kaufmann",
    "Fachfrau": "Fachmann",
}
_MASCULINE_ENDINGS = ("er", "ist", "ent", "ant", "or", "eur", "at", "og", "graph")


def _masculine_word(word: str) -> str:
    """Ein Rollenwort in die maennliche Form bringen."""
    if word in _MASCULINE_WORDS:
        return _MASCULINE_WORDS[word]
    if word.endswith("frau") and len(word) > 5:
        return f"{word[:-4]}mann"
    if word.endswith("innen") and len(word) > 7:
        stem = word[:-5]
        if stem.endswith(_MASCULINE_ENDINGS):
            return stem
        return f"{stem}en"
    if word.endswith("in") and len(word) > 4:
        stem = word[:-2]
        if stem.endswith(_MASCULINE_ENDINGS):
            return stem
    return word


def masculine_form(value: str | None) -> str:
    """Weibliche Berufsbezeichnungen in die maennliche Form setzen."""
    if not value:
        return ""
    return re.sub(
        r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-]*",
        lambda match: _masculine_word(match.group(0)),
        str(value),
    )


def clean_job_title(value: str | None) -> str:
    """Stellentitel ohne Gendermarken und Anbieter-IDs, in maennlicher Form."""
    text = str(value or "")
    if not text.strip():
        return ""
    text = _GENDER_MARKER.sub("", text)
    text = _GENDER_BARE.sub("", text)
    text = _GENDER_SUFFIX.sub("", text)
    text = _ID_REFERENCE.sub("", text)
    text = _PAREN_NUMBER.sub("", text)
    text = _PAREN_CODE.sub("", text)
    text = _HASH_NUMBER.sub("", text)
    text = re.sub(r"[\(\[]\s*[\)\]]", "", text)
    text = masculine_form(text)
    text = re.sub(r"\s*[–\-|/]\s*$", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" ,;–-")
    return text or str(value).strip()


def clean_job_text(value: str | None) -> str:
    """Beschreibung ohne Gendermarken und reine Anbieter-IDs, maennliche Form."""
    text = str(value or "")
    if not text.strip():
        return ""
    text = _GENDER_MARKER.sub("", text)
    text = _GENDER_BARE.sub("", text)
    text = _GENDER_SUFFIX.sub("", text)
    text = _ID_REFERENCE.sub("", text)
    text = _PAREN_NUMBER.sub("", text)
    text = _PAREN_CODE.sub("", text)
    text = _HASH_NUMBER.sub("", text)
    text = re.sub(r"[\(\[]\s*[\)\]]", "", text)
    text = masculine_form(text)
    lines: list[str] = []
    for line in text.splitlines():
        cleaned = re.sub(r"[ \t]{2,}", " ", line).strip(" ,;–-")
        if cleaned:
            lines.append(cleaned)
        elif lines and lines[-1] != "":
            lines.append("")
    return "\n".join(lines).strip()
