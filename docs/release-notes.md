## AutoApplication 1.0.3

Die KI schreibt die Bewerbung und liest die Anzeige aus.

### Neu

- **Anzeige auslesen.** Titel, Beschreibung und Bewerbungsadresse kommen aus der
  KI. Zusätze ohne Bezug zur Stelle – `(m/w/d)`, `(gn*)`, `(all genders)`,
  Inserats-, Referenz- und Job-IDs – werden entfernt; Berufsbezeichnungen stehen
  immer in der männlichen Form. Ohne KI erledigt das eine lokale Bereinigung.
- **Mailtext von der KI.** Betreff und Text des Entwurfs werden pro Stelle
  geschrieben, mit Bezug auf Anforderungen, Fähigkeiten und Interessen. Die
  Vorlage dient als Stilvorgabe und bleibt der Rückfall.
- **Anschreiben als PDF.** Die KI schreibt ein Anschreiben; es wird als PDF im
  Ordner `anschreiben` abgelegt und als erster Anhang mitgeschickt. Abschaltbar
  unter Einstellungen → Unterlagen.
- **Empfängeradresse.** Die Bewerbungsadresse wird aus der Anzeige gelesen und
  für den Entwurf verwendet.

## AutoApplication 1.0.2

Google-Anmeldung ohne Client-Geheimnis.

### Neu

- **Google-Login im Browser.** „Google-Konto verbinden“ öffnet die normale
  Google-Anmeldung; nach der Freigabe kommt die Antwort über einen lokalen
  Rückkanal zurück (OAuth 2.0 mit PKCE und `http://127.0.0.1`). Ein
  Client-Geheimnis wird weder eingetragen noch gespeichert – der OAuth-Client
  ist vom Typ „Desktop app“.
- Das Feld „Client-Geheimnis“ ist aus den Einstellungen entfernt; es genügt die
  Client-ID des Desktop-Clients.

## AutoApplication 1.0.1

Mehr Kontrolle über Abruf und Anbindungen.

### Neu

- **Stellen-API ein- und ausschaltbar.** Unter **Einstellungen → Suche** lässt
  sich der Abruf bei ostjob.ch abschalten – standardmässig ist er **aus**. Ohne
  Häkchen fragt AutoApplication die API weder beim Start noch im Tageslauf noch
  über „Jetzt Stellen suchen“ ab; ein Hinweis führt direkt zu den Einstellungen.
- **Google-Konto verbinden.** Unter **Einstellungen → Google** lässt sich ein
  Google-Konto per Gerätecode anmelden. Bewerbungen landen dann als Entwurf in
  Gmail, Versand und Antworten werden wie bei Outlook verfolgt. Die
  E-Mail-Anbindung (Outlook, Google oder keine) wird daneben gewählt.
- **Groq als KI.** Unter **Einstellungen → KI** ist Groq als Anbieter wählbar;
  Adresse und Modell werden vorgeschlagen, der Schlüssel kommt aus dem Feld oder
  aus `GROQ_API_KEY`.
- **Interessen und Fähigkeiten.** Zwei getrennte Stichwortfelder im Profil. Sie
  müssen sich nicht decken und stehen der KI-Auswertung sowie den Vorlagen als
  `{interessen}` und `{faehigkeiten}` zur Verfügung.
- **Klickbare Übersicht.** Die Kennzahl-Kacheln führen direkt in die passende
  Ansicht: neue und passende Stellen zu den Stellen, Entwürfe, offene Antworten
  und eingegangene Antworten zu den Bewerbungen.

## AutoApplication 1.0.0

Stellen von ostjob.ch suchen, Bewerbungen als Outlook-Entwurf vorbereiten und
Antworten bis zur Zusage verfolgen.

### Funktionen

- **Täglicher Lauf:** Holt die neuesten Stellen von ostjob.ch, filtert nach
  Suchbegriffen, Ort samt Umkreis, Pensum, Arbeitsweg, Kanton, Alter der Anzeige
  und Ausschluss-Stichworten. Bekannte Stellen werden nicht doppelt bearbeitet.
- **Stichworte und Vorlage:** Jede Anzeige wird in Stichworte zerlegt – per
  KI (OpenAI-kompatible Schnittstelle) oder lokal aus den Portalangaben. Passt
  eine Stelle auf mindestens zwei Stichworte einer Vorlage, entsteht daraus das
  Anschreiben. Vorlagen: Spedition und Logistik, Tapetenwechsel, Lager und
  Produktion sowie eine Nachfrage-Vorlage; alle im Programm bearbeitbar.
- **Entwurf statt Versand:** Die Bewerbung landet samt Anhängen (Lebenslauf,
  Zeugnisse, Diplome) im Ordner „Entwürfe“ von Outlook. Geprüft und gesendet
  wird von Hand.
- **Versand erkannt:** Verschwindet der Entwurf aus den Entwürfen und taucht in
  „Gesendete Elemente“ auf, trägt AutoApplication das Datum in die
  Bewerbungstabelle ein.
- **Antworten ausgewertet:** Das Postfach wird auf Antworten der Firma geprüft –
  über die Unterhaltung, die Absenderdomain, den Firmennamen oder den
  Stellentitel. Absagen archivieren die Bewerbung, Zusagen und Einladungen
  erscheinen als Hinweis.
- **Nachfragen:** Ohne Antwort nach 14 Tagen legt AutoApplication eine
  Nachfrage nach Vorlage als Entwurf bereit – einmal je Bewerbung.
- **Stilles Update:** Beim Start prüft AutoApplication die GitHub-Releases, lädt
  den Installer im Hintergrund und ersetzt die Installation ohne Assistent.
  Abschaltbar über `--no-update` oder `AUTOAPPLICATION_NO_UPDATE=1`.

### Installation

`AutoApplication-1.0.0-Setup.exe` herunterladen und ausführen. Windows 10 und 11,
kein Administrator- und kein Python-Zubehör nötig.

### Einrichtung

- Unter **Einstellungen → Suche** Suchbegriffe, Ort, Umkreis, Pensum und
  Arbeitsweg eintragen.
- Für Outlook eine App-Registrierung bei Microsoft Entra anlegen (öffentlicher
  Client, Delegierte Berechtigungen Mail.ReadWrite, Mail.Send, User.Read) und
  die Client-ID unter **Einstellungen → Outlook** eintragen, dann „Anmelden“.
- Die KI ist optional. Ohne Schlüssel arbeitet AutoApplication mit den
  Stichworten des Portals und der Vorlagen weiter.

### Geprüft

- 73 automatisierte Tests für Portalabruf und Filter, Vorlagenauswahl und
  Platzhalter, Stichworte und Antwortauswertung, Ablage und Statuswechsel,
  Nachfrist, Outlook-Aufrufe (mit Attrappe), Unterlagen und Update-Vergleich.
- Selbsttest der gepackten Anwendung (`AutoApplication --self-test`) im
  Windows-Build.

### Hinweis

Die Stellensuche nutzt die JSON-Schnittstelle von ostjob.ch. Ändert das Portal
Adresse oder Format, meldet AutoApplication das im Protokoll, statt still
nichts zu tun. Bewerbungen an Portale ohne E-Mail-Adresse bleiben als Entwurf
ohne Empfänger stehen; die Adresse wird dann von Hand ergänzt.
