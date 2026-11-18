## AutoApplication 1.0.14

Übersicht im Tab Bewerbungen: Posteingang auf Klick prüfen, Kennungen
nachschauen und eine Statuszeile, die bei schmalem Fenster umbricht.

### Neu

- **„E-Mail-Eingang jetzt prüfen“ im Tab Bewerbungen.** Der Knopf gleicht
  gesendete Bewerbungen und eingegangene Antworten sofort ab – ohne Umweg über
  die Übersicht.
- **Kennung im Dialog „Anschreiben anzeigen“.** Über dem Brieftext steht die
  Kennung der Bewerbung (z. B. `AA-7K4P-Q9XM-3TRZ`) zum Markieren und Kopieren.
  Damit lässt sich bei einer falsch zugeordneten Antwort nachsehen, welche
  Kennung die Bewerbung trägt.
- **Protokoll zeigt den Weg der Zuordnung.** Jede verbuchte Antwort nennt im
  Protokoll, wodurch sie zugeordnet wurde: «zugeordnet über Kennung …»,
  «Unterhaltung», «Absenderdomain …», «Firmenname» oder «Stellentitel». So ist
  erkennbar, ob die Kennung greift oder nur ein Rückfall.

### Geändert

- **Status-Häkchen brechen um.** Die Zeile mit den acht Häkchen und dem Zähler
  setzt bei schmalem Fenster oder grösserer Schrift in die nächste Zeile um,
  statt rechts abgeschnitten zu werden (neu dafür: ein umbrechendes Layout).
  Geprüft bei 420–1200 px Fensterbreite mit 9 pt und 13 pt Schrift: alle acht
  Häkchen und der Zähler bleiben vollständig sichtbar, die Tabelle beginnt
  jeweils unter der letzten Zeile.

## AutoApplication 1.0.13

Die Bewerbungsmail geht an die richtige Adresse und spricht die richtige Person
an – notfalls nach einer kurzen Rückfrage.

### Neu

- **Kontaktdaten stehen im Entwurf.** E-Mail-Adresse und Ansprechperson werden
  aus der Anzeige gelesen und beim Vorbereiten in den Entwurf übernommen; die
  Adresse steht bereits im Feld «An» des Entwurfs.
- **Texterkennung für Bilder.** Nennen Anzeigen den Kontakt nur in einem Bild,
  liest die unter Windows eingebaute Texterkennung den Text aus den Bildern der
  Anzeige und sucht darin nach Adresse und Ansprechperson.
- **Rückfrage vor dem Entwurf.** Fehlt die Adresse oder die Ansprechperson auch
  danach, erscheint vor dem Erzeugen der Mail ein Fenster: E-Mail-Adresse und
  Ansprechperson («Herr …» oder «Frau …») eingeben, danach entsteht der Entwurf.
  Die Angaben bleiben bei der Stelle gespeichert.

### Geändert

- Verschleierte Adressen wie `personal [at] firma [dot] ch` werden erkannt.
- «Herrn Müller» wird als «Herr Müller» übernommen; Titel wie «Dr.» fallen bei
  der Anrede weg.

## AutoApplication 1.0.12

Die Vorlagen nennen jetzt die echten Stationen; die Erfahrungsjahre haben einen
sinnvollen Standard.

### Geändert

- **Erfahrung stimmt mit dem Lebenslauf.** Statt «zuletzt als Shipping Officer»
  stehen die tatsächlichen Stationen: Shipping Officer bei der Escatec
  Switzerland AG (über elf Jahre), davor Emons Transporte und Schenker Schweiz
  (Luftfracht), seit Juli 2026 Techniker bei der Keller & Dürr Kassensysteme AG.
  Ausbildung als Informatiker (Leica) und Spediteur, User Help Desk bei Hilti
  sowie die Sprachkenntnisse bleiben wie im Lebenslauf.
- **Neuer Standard für die Erfahrungsjahre:** «über zwanzig» statt «acht» – die
  Berufserfahrung reicht von 2003 bis heute. Der alte Vorgabewert «acht» wird
  beim Start ersetzt; ein selbst gesetzter Wert bleibt unverändert.
- Bestehende `vorlagen.json` wird auf Revision 3 gehoben; eigene Vorlagen und
  selbst bearbeitete Standardvorlagen bleiben unangetastet.

## AutoApplication 1.0.11

Das Anschreiben sieht aus wie ein normaler Brief und passt ins Fenstercouvert.

### Geändert

- **Empfängeradresse im Couvertfenster.** Der Empfängerblock beginnt 2,2 cm vom
  linken Rand und 4,6 cm unter dem oberen Rand – dort, wo das Fenster eines
  Fenstercouverts sitzt (Fenster links).
- **Absenderadresse oben links in Textgrösse.** Name, Strasse, Ort und Kontakt
  stehen in derselben Schriftgrösse und Farbe (schwarz) wie der Brieftext.
- **Ohne Linien und ohne Fusszeile.** Die Trennstriche über und unter dem Brief
  sowie die Fusszeile mit Seitenzahl sind entfernt.

## AutoApplication 1.0.10

Jede Bewerbung trägt eine einmalige, unsichtbare Kennung – Antworten werden
damit sicher zugeordnet.

### Neu

- **Einmalige Kennung je Bewerbung.** Beim Vorbereiten entsteht eine zufällige
  Kombination aus Buchstaben, Ziffern und Bindestrichen, z. B.
  `AA-7K4P-Q9XM-3TRZ`. Sie wird in der Ablage gespeichert und reist in jeder
  Mail mit – auch in der Nachfrage.
- **Unsichtbar in der Mail.** Die Kennung steht im HTML-Teil ganz unten als
  weisser Text in Schriftgrösse 0, zusätzlich als HTML-Kommentar und im
  Mailkopf `X-AutoApplication-Ref`. Der reine Text-Teil bleibt frei davon; der
  Empfänger sieht nichts.
- **Sichere Zuordnung.** Beim Prüfen des Posteingangs liest AutoApplication die
  Kennung aus den Kopfzeilen (`References`, `In-Reply-To`), aus dem zitierten
  HTML-Teil oder aus dem Mailtext und ordnet die Antwort der richtigen
  Bewerbung zu – auch wenn Betreff, Absender und Unterhaltung nicht passen.
  Unterhaltung, Absenderdomain, Firmenname und Stellentitel bleiben als
  Rückfall erhalten.

## AutoApplication 1.0.9

Statusfilter im Tab Bewerbungen als Häkchen – einzeln und kombiniert.

### Neu

- **Filter per Häkchen.** Statt der Auswahlliste stehen im Tab „Bewerbungen“
  alle möglichen Status als Kontrollkästchen: Entwurf, Gesendet, Nachgefragt,
  Einladung, Zusage, Absage, Archiviert und Antwort. Jedes Häkchen lässt sich
  allein setzen, mehrere zusammen zeigen die Bewerbungen aller gewählten
  Status. Ohne Häkchen bleibt die ganze Liste sichtbar; der Zähler nennt
  zusätzlich, wenn gefiltert wird.
- Die Ablage fragt die Status jetzt mit einer einzigen Abfrage ab
  (`IN (...)`), damit die Kombination auch bei vielen Bewerbungen schnell bleibt.

## AutoApplication 1.0.8

Mehr Vorlagen aus dem Lebenslauf und ein einheitliches Anschreiben im
Geschäftsbrief-Layout.

### Neu

- **Sieben Vorlagen statt drei.** Neu sind „Export, Zoll und Aussenhandel“,
  „Technischer Kundendienst und Kassensysteme“, „IT-Support und
  Anwenderbetreuung“ sowie „Kundenberatung und Verkaufsinnendienst“;
  „Spedition und Logistik“, „Lager und Kommissionierung“ und „Administration und
  Sachbearbeitung“ (früher „Tapetenwechsel“) sind überarbeitet. Die Stichworte
  decken die bisherigen Tätigkeiten ab: Disposition, Exportkontrolle,
  Zolldokumente, ERP (Infor Cloud Suite), Kommissionierung, Kassensysteme/POS,
  Helpdesk, Kundenberatung und Büroorganisation.
- **Texte mit Substanz.** Die Vorlagen nennen, was tatsächlich gemacht wurde –
  Shipping Officer bei Escatec, Export- und Zolldokumente, Installation und
  Fernwartung von Kassensystemen, Schulungen, Sprachkenntnisse – statt
  allgemeiner Sätze. Die strenge Passungsregel bleibt.
- **Anschreiben im Geschäftsbrief-Layout.** Briefkopf mit Name und Kontaktdaten,
  Trennlinie, Ort und Datum rechts, Empfängerblock, fetter Betreff, saubere
  Absätze, Grussformel mit Namen sowie Fusszeile mit Seitenzahl. Die
  Schlussformel aus Vorlage oder KI wird nicht doppelt gesetzt.
- **Bestehende `vorlagen.json`** wird beim Start auf die neue Fassung gehoben:
  mitgelieferte Vorlagen werden ersetzt, neue ergänzt; eigene Vorlagen und
  bearbeitete Standardvorlagen bleiben unangetastet.

## AutoApplication 1.0.7

Anreden mit Namen, Entwürfe nur auf Klick und strengere Stellenpassung.

### Neu

- **Anrede mit Ansprechperson.** Nennt die Anzeige „Herr …“ oder „Frau …“,
  beginnt Mail und Anschreiben mit „Sehr geehrter Herr Müller“ bzw.
  „Sehr geehrte Frau Meier“. Ohne klare Angabe bleibt es bei „Sehr geehrte
  Damen und Herren“ – geraten wird nicht. Der neue Platzhalter `{anrede}`
  steht in allen Vorlagen, `{ansprechperson}` liefert den Namen.
- **Keine automatischen Entwürfe mehr.** Der Tageslauf merkt passende Stellen
  nur vor; Betreff, Mailtext und Anschreiben entstehen erst mit
  „E-Mail vorbereiten“ in der Stellenliste. Auch Nachfragen werden nur noch
  auf Klick erzeugt.
- **Strengere Passung.** Eine Stelle gilt nur als passend, wenn ein
  Vorlagen-Stichwort im Titel steht oder deutlich mehr Stichworte in der
  Anzeige vorkommen. Die Vorlage „Lager und Produktion“ enthält keine
  allgemeinen Industriebegriffe (Produktion, Montage, Maschinenbedienung)
  mehr – damit fallen branchenfremde Anzeigen (z. B. Metallverarbeitung)
  heraus.
- Bestehende `vorlagen.json` wird beim Start automatisch nachgezogen
  (Anrede-Platzhalter, bereinigte Stichworte).

## AutoApplication 1.0.6

Gmail ohne Microsoft-Konto: neue Anbindung über IMAP und SMTP mit App-Passwort.

### Neu

- **Gmail (IMAP/SMTP, App-Passwort)** als E-Mail-Anbindung. Unter Einstellungen
  → Gmail werden Adresse und das 16-stellige App-Passwort eingetragen; mit
  „Verbindung testen“ lassen sich IMAP- und SMTP-Anmeldung prüfen.
- **Entwürfe landen direkt in Gmail** (Ordner „Entwürfe“, per IMAP APPEND) und
  erscheinen damit auch in Outlook, das das Konto abruft. Gesendet wird über
  `smtp.gmail.com:587`.
- **Versand und Antworten** werden über den Ordner „Gesendet“ und den
  Posteingang verfolgt – gleiche Abläufe wie bei Outlook.
- Kein Google-Cloud-Projekt, keine Client-ID, kein Client-Geheimnis; das
  App-Passwort bleibt lokal in `einstellungen.json`.

### Hinweise

- App-Passwörter setzen eine aktive 2-Faktor-Authentifizierung voraus
  (Google-Konto → Sicherheit → App-Passwörter). Bei Advanced Protection oder
  einer Workspace-Sperre sind sie nicht verfügbar.
- Microsoft Graph bleibt für Outlook zuständig; ein in Outlook hinzugefügtes
  Gmail-Konto ist für Graph weiterhin nicht erreichbar.

## AutoApplication 1.0.5

Google-Anbindung entfernt – AutoApplication nutzt Outlook (Microsoft Graph).

### Geändert

- **Google (Gmail) ist aus den E-Mail-Optionen entfernt.** Unter Einstellungen →
  E-Mail-Anbindung stehen nur noch „Outlook (Microsoft Graph)“ und „Keine – nur
  im Programm“. Die Felder Client-ID und Client-Geheimnis für Google sind weg,
  ebenso `google_token.json` und die Google-Anmeldung.
- Bestehende Einstellungen bleiben gültig; ein früher gewähltes Google-Konto
  wird auf „Outlook“ zurückgesetzt.
- README und Anmeldedialog beschreiben nur noch Outlook.

### Hinweis

- Microsoft Graph greift ausschliesslich auf Microsoft-Postfächer zu. Ein in
  Outlook hinzugefügtes Gmail-Konto ist für AutoApplication nicht erreichbar:
  Entwürfe, Versand und Antwortprüfung laufen über das angemeldete
  Microsoft-Konto. Für Gmail wäre die Google-Anbindung nötig.

## AutoApplication 1.0.4

Google-Anmeldung läuft jetzt vollständig durch.

### Neu

- **Client-Geheimnis wieder eintragbar.** Google verlangt beim Desktop-Client
  das Client-Geheimnis beim Token-Tausch – auch mit PKCE (geprüft: ohne Secret
  antwortet der Token-Endpunkt mit „client_secret is missing“). Das Feld steht
  unter Einstellungen → Google, wird lokal in `einstellungen.json` gespeichert
  und nur an Google gesendet. Ins Repository gehört es nicht.
- **Anmeldung und Erneuerung** senden das Geheimnis mit, sodass der
  Browser-Login und die automatische Token-Erneuerung funktionieren.
- Hinweis zur Google-Konsole: Desktop-Client, Gmail API aktiv, Berechtigung
  `gmail.modify` unter Data Access, bei externer Zielgruppe Testnutzer
  eintragen. Im Testing-Modus laufen Google-Freigaben nach sieben Tagen ab.

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
