"""Persoenliche Passung einer Stelle: Interessen und Faehigkeiten.

Die Vorlagenpassung sagt, ob eine Stelle zur bisherigen Richtung passt. Hier
kommt die persoenliche Sicht dazu: Was interessiert mich, und was kann ich
schon? Die Interessen wiegen bei der Auswahl mehr - gerade beim Branchenwechsel.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .text import has_term


def job_text(job: dict[str, Any]) -> str:
    """Alles, was fuer den Vergleich mit Interessen und Faehigkeiten zaehlt."""
    return " ".join(
        str(job.get(key) or "")
        for key in ("title", "company", "city", "description", "keywords")
    )


def matching_terms(text: str, terms: Iterable[str]) -> list[str]:
    """Welche der Stichworte kommen im Text vor?"""
    return [term for term in terms if has_term(text, term)]


def personal_match(
    job: dict[str, Any],
    interests: Iterable[str],
    skills: Iterable[str],
) -> tuple[list[str], list[str]]:
    """Treffer bei den Interessen und bei den Faehigkeiten."""
    text = job_text(job)
    return matching_terms(text, interests), matching_terms(text, skills)


def personal_fit(
    job: dict[str, Any],
    interests: Iterable[str],
    skills: Iterable[str],
) -> int | None:
    """Anteil der Profil-Stichworte in der Anzeige, in Prozent (0 bis 100).

    100 % heisst: Jedes hinterlegte Interesse und jede Faehigkeit kommt vor.
    Ohne Stichworte im Profil gibt es keinen Wert (``None``) - 0 % waere dort
    eine falsche Aussage.
    """
    interests = list(interests)
    skills = list(skills)
    total = len(interests) + len(skills)
    if total == 0:
        return None
    found_interests, found_skills = personal_match(job, interests, skills)
    return round(100 * (len(found_interests) + len(found_skills)) / total)


def priority_key(
    interests: list[str],
    skills: list[str],
    score: int,
    published: str = "",
) -> tuple[int, int, int, str]:
    """Sortierschluessel: Interessen vor Faehigkeiten, dann die Passung."""
    return (len(interests), len(skills), int(score or 0), published or "")
