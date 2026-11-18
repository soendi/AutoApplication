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

- 40 automatisierte Tests für Portalabruf und Filter, Vorlagenauswahl und
  Platzhalter, Stichworte und Antwortauswertung, Ablage und Statuswechsel,
  Nachfrist, Outlook-Aufrufe (mit Attrappe), Unterlagen und Update-Vergleich.
- Selbsttest der gepackten Anwendung (`AutoApplication --self-test`) im
  Windows-Build.

### Hinweis

Die Stellensuche nutzt die JSON-Schnittstelle von ostjob.ch. Ändert das Portal
Adresse oder Format, meldet AutoApplication das im Protokoll, statt still
nichts zu tun. Bewerbungen an Portale ohne E-Mail-Adresse bleiben als Entwurf
ohne Empfänger stehen; die Adresse wird dann von Hand ergänzt.
