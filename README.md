# AutoApplication 1.0.0

Stellen von ostjob.ch suchen, Bewerbungen als Outlook-Entwurf vorbereiten und
Antworten bis zur Zusage verfolgen – als Windows-Programm mit stillen Updates.

## Was AutoApplication macht

1. **Stellen holen.** Jeden Tag (oder auf Klick) lädt AutoApplication die
   neuesten Anzeigen von ostjob.ch und filtert sie nach Suchbegriffen, Ort und
   Umkreis, Pensum, Arbeitsweg, Kanton, Alter der Anzeige und
   Ausschluss-Stichworten. Bereits bekannte Stellen bleiben einmalig in der
   Ablage und werden nicht doppelt bearbeitet.
2. **Stichworte bestimmen.** Die Beschreibung wird in Stichworte zerlegt – per
   KI über eine OpenAI-kompatible Schnittstelle oder, ohne Schlüssel, lokal aus
   den Portalangaben und dem Stichwortverzeichnis der Vorlagen.
3. **Vorlage wählen.** Passt eine Stelle auf mindestens zwei Stichworte einer
   Vorlage, wird daraus das Anschreiben. Beispiel: „Spedition“ und
   „Disposition“ ergeben die Speditionsvorlage; „Sachbearbeitung“ und
   „Kundendienst“ die Vorlage „Tapetenwechsel“. Reicht die Passung nicht, bleibt
   die Stelle ohne Bewerbung.
4. **Entwurf statt Versand.** Die Bewerbung wird mit Betreff, Anschreiben und
   den Unterlagen aus dem Unterlagenordner (Lebenslauf, Zeugnisse, Diplome) als
   **Entwurf in Outlook** abgelegt. Geprüft und gesendet wird von Hand.
5. **Versand erkennen.** Taucht die Mail in „Gesendete Elemente“ auf, steht das
   Versanddatum in der Bewerbungstabelle.
6. **Antworten auswerten.** Das Postfach wird auf Antworten der Firma geprüft –
   über die Unterhaltung, die Absenderdomain, den Firmennamen oder den
   Stellentitel. Eine **Absage** archiviert die Bewerbung, eine **Zusage** oder
   **Einladung** erscheint als Hinweis.
7. **Nachfassen.** Ohne Antwort nach 14 Tagen legt AutoApplication eine
   Nachfrage nach Vorlage als Entwurf bereit – einmal je Bewerbung.

## Installation

`AutoApplication-1.0.0-Setup.exe` von der
[Release-Seite](https://github.com/soendi/AutoApplication/releases/latest)
herunterladen und ausführen. Windows 10 und 11, kein Administrator- und kein
Python-Zubehör nötig.

Beim Start prüft AutoApplication im Hintergrund die GitHub-Releases. Steht eine
neue Fassung bereit, wird der Installer geladen und **still** eingespielt: das
Programm schliesst sich, das Setup ersetzt die Dateien und öffnet
AutoApplication wieder. Abschalten mit `--no-update` oder
`AUTOAPPLICATION_NO_UPDATE=1`.

## Einrichtung

### Suche

Unter **Einstellungen → Suche** eintragen:

| Feld | Bedeutung |
| --- | --- |
| Suchbegriffe | Ein Begriff pro Zeile, z. B. `Spedition`, `Logistik` |
| Ort / placeCode / placeValue | Ortsangabe aus ostjob.ch, z. B. `Balgach 9436 (SG)` / `balgach-sg-9436` |
| Breiten-/Längengrad | Für Umkreis und Arbeitsweg, z. B. `47.4055` / `9.6087` |
| Umkreis der Suche | Umkreis, den das Portal durchsucht |
| Arbeitsweg höchstens | Luftlinie, die eine Anzeige höchstens entfernt sein darf |
| Pensum von/bis | 60–100 lässt 80-%-Stellen zu, 100-%-Stellen fallen bei „bis 90“ heraus |
| Kantone | Leer = alle; sonst z. B. `St. Gallen, Thurgau` |
| Nicht anzeigen | Ausschluss-Stichworte, mit Komma getrennt |

### Outlook (Microsoft Graph)

AutoApplication meldet sich ohne Passwort im Programm an (Gerätecode):

1. Im [Microsoft Entra Admin Center](https://entra.microsoft.com) eine
   **App-Registrierung** anlegen; Kontotypen „Konten in einem beliebigen
   Organisationsverzeichnis und persönliche Microsoft-Konten“.
2. Unter **Authentifizierung** die Plattform „Mobile and desktop applications“
   wählen und **„Öffentliche Clientflows zulassen“ auf Ja** stellen. Ein
   Redirect-URI wird für den Gerätecode nicht gebraucht.
3. Unter **API-Berechtigungen** delegierte Berechtigungen `Mail.ReadWrite`,
   `Mail.Send`, `User.Read` hinzufügen und die Zustimmung erteilen.
4. Die **Client-ID** unter **Einstellungen → Outlook** eintragen, Mandant
   `common` lassen, „Anmelden“ wählen und den angezeigten Code auf der
   Microsoft-Seite bestätigen.

Die Anmeldung wird in `outlook_token.json` im Benutzerordner gespeichert (nur
für den eigenen Benutzer lesbar) und automatisch erneuert. „Trennen“ löscht sie.

### KI (optional)

Unter **Einstellungen → KI** Adresse einer OpenAI-kompatiblen Schnittstelle
(z. B. `https://api.openai.com/v1`), Modell und Schlüssel eintragen. Der
Schlüssel lässt sich auch über die Umgebungsvariable
`AUTOAPPLICATION_AI_KEY` (oder `OPENAI_API_KEY`) bereitstellen.

Ohne KI bleibt alles nutzbar: die Stichworte kommen dann aus den
Portalangaben und dem Stichwortverzeichnis der Vorlagen, die Antwortauswertung
arbeitet mit typischen Formulierungen.

### Unterlagen

Unter **Einstellungen → Unterlagen** den Ordner mit Lebenslauf, Zeugnissen und
Diplomen wählen. Alle PDF-, Word- und Bilddateien darin werden angehängt –
Dateien mit „Lebenslauf“, „Zeugnis“ oder „Diplom“ im Pfad zuerst. Die
Gesamtgrösse ist begrenzt (Standard 20 MB); einzelne Anhänge über 3 MB lässt
Microsoft Graph nicht als einfachen Anhang zu und werden ausgelassen.

## Vorlagen

Unter **Vorlagen** lassen sich Name, Stichworte, Betreff und Text bearbeiten,
neue Vorlagen anlegen und die Standardvorlagen wiederherstellen. Eine Vorlage
gilt für Nachfragen, wenn das Häkchen gesetzt ist.

Platzhalter in Betreff und Text:

| Platzhalter | Inhalt |
| --- | --- |
| `{titel}` | Stellentitel |
| `{firma}` | Firmenname |
| `{ort}` | Arbeitsort |
| `{pensum}` | Pensum aus der Anzeige |
| `{stellen_id}` | Inseratsnummer |
| `{datum}` | heutiges Datum |
| `{vorname}`, `{nachname}`, `{strasse}`, `{plz}`, `{wohnort}`, `{telefon}`, `{email}` | Angaben aus dem Profil |
| `{erfahrung}` | „Jahre Erfahrung“ aus dem Profil (z. B. `acht`) |
| `{verfuegbar}` | Verfügbarkeit aus dem Profil |
| `{bewerbungsdatum}`, `{tage}` | nur in der Nachfrage-Vorlage |

## Automatik

- **Täglicher Lauf** zur eingestellten Uhrzeit: Stellen suchen, Entwürfe
  anlegen, Versand prüfen, Antworten auswerten, Nachfragen vorbereiten.
- **Beim Start** läuft der Tageslauf einmal, wenn er heute noch nicht lief.
- **Postfach prüfen** und **Nachfragen vorbereiten** gehen auch von Hand.

Der Tageslauf lässt sich ohne Fenster starten – etwa aus der
Windows-Aufgabenplanung:

```
AutoApplication.exe --run-daily
```

## Wo die Daten liegen

Alles im Benutzerordner `%USERPROFILE%\AutoApplication` (Linux/macOS:
`~/AutoApplication`):

| Datei | Inhalt |
| --- | --- |
| `einstellungen.json` | Profil, Suche, KI, Outlook, Automatik |
| `daten.db` | Stellen, Bewerbungen, Antworten, Protokoll (SQLite) |
| `vorlagen.json` | Vorlagen |
| `outlook_token.json` | Anmeldung bei Microsoft (nur eigener Benutzer) |
| `autoapplication.log` | Protokoll für die Fehlersuche |

Für Tests lässt sich der Ordner über `AUTOAPPLICATION_HOME` umlenken.

## Entwicklung

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
PYTHONPATH=src .venv/bin/python -m pytest tests -q
PYTHONPATH=src .venv/bin/python -m autoapplication --self-test
PYTHONPATH=src .venv/bin/python -m autoapplication
```

Aufbau:

```
src/autoapplication/
  app.py              Start, Selbsttest, Tageslauf ohne Fenster
  core/               Konfiguration, Ablage, ostjob.ch, KI, Vorlagen, Outlook, Ablauf, Updater
  data/templates.json Standardvorlagen
  ui/                 Oberfläche (PySide6)
packaging/            PyInstaller-Spec, Inno-Setup, Build-Skript, Symbol
.github/workflows/    Installer bauen, Tag und Release anlegen
```

## Bauen und Veröffentlichen

Reihenfolge wie bei den bisherigen Programmen:

1. Version an drei Stellen anheben: `src/autoapplication/__init__.py`,
   `pyproject.toml` und `packaging/installer.iss` (Standardwert).
2. Commit und Push.
3. **Installer bauen:** im GitHub-Actions-Workflow „Installer bauen und ans
   Release hängen“ *Run workflow* mit der Version (z. B. `1.0.0`). Der
   Windows-Lauf installiert die Abhängigkeiten, führt die Tests aus, baut mit
   PyInstaller, prüft die gebaute Anwendung per Selbsttest und erstellt
   `AutoApplication-<Version>-Setup.exe` mit Inno Setup.
4. **Release und Tag:** Derselbe Workflow legt danach Tag `v<Version>` und
   Release an und hängt den Installer an.

Lokal auf Windows:

```
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

Das Skript braucht Python und Inno Setup 6 (`ISCC.exe`).

## Grenzen

- Die Stellensuche nutzt die JSON-Schnittstelle von ostjob.ch. Ändert das
  Portal Adresse oder Format, steht das im Protokoll – es wird nicht still
  nichts getan.
- Nicht jede Anzeige nennt eine E-Mail-Adresse. Dann bleibt der Entwurf ohne
  Empfänger stehen und die Adresse wird von Hand ergänzt (oder die
  Online-Bewerbung im Feld „Stelle öffnen“ benutzt).
- Die Antwortauswertung ist eine Einordnung, keine Rechtsauskunft: Absagen und
  Zusagen werden erkannt, Sonderfälle bleiben als „Antwort“ stehen.
