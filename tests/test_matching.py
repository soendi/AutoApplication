from __future__ import annotations

from autoapplication.core.matching import (
    matching_terms,
    personal_fit,
    personal_match,
    priority_key,
)


def _job(**overrides) -> dict:
    values = {
        "title": "Speditionskaufmann",
        "company": "Muster Logistik AG",
        "city": "Balgach",
        "description": "Disposition, Transport und Zoll",
        "keywords": '["Spedition", "Zoll"]',
    }
    values.update(overrides)
    return values


def test_personal_match_separates_interests_and_skills() -> None:
    interests, skills = personal_match(
        _job(),
        ["Zoll", "Technik"],
        ["Disposition", "SAP"],
    )
    assert interests == ["Zoll"]
    assert skills == ["Disposition"]


def test_interests_count_even_without_template_fit() -> None:
    # Branchenwechsel: die Stelle passt auf keine Vorlage, interessiert aber.
    job = _job(title="Techniker Kassensysteme", description="Montage und Service")
    interests, skills = personal_match(job, ["Technik"], ["Disposition"])
    assert interests == ["Technik"]
    assert skills == []


def test_priority_prefers_interests_over_skills() -> None:
    with_interests = priority_key(["Zoll"], [], 1, "2026-11-18")
    with_skills = priority_key([], ["Disposition", "SAP", "ERP"], 9, "2026-11-18")
    assert with_interests > with_skills
    # Bei gleichen Interessen entscheiden die Faehigkeiten, dann die Passung.
    assert priority_key(["Zoll"], ["SAP"], 2) > priority_key(["Zoll"], [], 9)


def test_personal_fit_counts_all_profile_terms() -> None:
    job = _job()
    # Zwei von vier Stichworten kommen vor.
    assert personal_fit(job, ["Zoll", "Technik"], ["Disposition", "SAP"]) == 50
    # Alles kommt vor -> 100 %, nichts -> 0 %.
    assert personal_fit(job, ["Zoll"], ["Disposition"]) == 100
    assert personal_fit(job, ["Technik"], ["SAP"]) == 0
    # Ohne Stichworte im Profil gibt es keinen Wert.
    assert personal_fit(job, [], []) is None


def test_matching_terms_ignores_case() -> None:
    assert matching_terms("Zoll und Disposition", ["zoll"]) == ["zoll"]
    assert matching_terms("", ["Zoll"]) == []
