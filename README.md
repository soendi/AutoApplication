# AutoApplication 1.0.29

Stellen von ostjob.ch suchen, Bewerbungen als Entwurf in Outlook oder Gmail
vorbereiten und Antworten bis zur Zusage verfolgen – als Windows-Programm mit
stillen Updates.

## Was AutoApplication macht

1. **Stellen holen.** Jeden Tag (oder auf Klick) lädt AutoApplication die
   neuesten Anzeigen von ostjob.ch und filtert sie nach Suchbegriffen, Ort und
   Umkreis, Pensum, Arbeitsweg, Kanton, Alter der Anzeige und
   Ausschluss-Stichworten. Bereits bekannte Stellen bleiben einmalig in der
   Ablage und werden nicht doppelt bearbeitet. Die Abfrage der Stellen-API ist
   standardmässig **aus** und wird unter **Einstellungen → Ostjob** eingeschaltet.
2. **Anzeige auslesen.** Die KI liest Titel, Beschreibung und Bewerbungsadresse
   aus der Anzeige. Zusätze ohne Bezug zur Stelle – Gendermarken wie `(m/w/d)`
   oder `(gn*)`, Inserats-, Referenz- und Job-IDs – fallen weg; die
   Berufsbezeichnung steht immer in der männlichen Form. Anschliessend werden
   Stichworte bestimmt (per KI oder lokal aus den Portalangaben und dem
   Stichwortverzeichnis der Vorlagen). Interessen und Fähigkeiten aus dem Profil
   fliessen in die Auswertung ein.
3. **Vorlage wählen.** Eine Stelle gilt als passend, wenn ein Stichwort der
   Vorlage im Titel steht oder deutlich mehr Stichworte in der Anzeige
   vorkommen.    Beispiel: „Spedition“ und „Disposition“ ergeben die
   Speditionsvorlage; „Sachbearbeitung“ und „Kundendienst“ die Vorlage
   „Administration und Sachbearbeitung“. Reicht die Passung nicht, greift die
   **Allgemeine Vorlage**; so entsteht für jede Stelle ein Anschreiben. Solche
   Stellen erhalten den Status **Allgemein**, damit **Passend** nur echte
   Treffer zeigt. Passende Stellen werden nur vorgemerkt.
4. **Entwurf auf Klick.** Erst wenn du eine Stelle in der Liste auswählst und
   **„E-Mail vorbereiten“** wählst, schreibt die KI Betreff und Mailtext sowie
   ein Anschreiben, das als PDF angehängt wird. Das PDF sieht aus wie ein
   normaler Brief: Absenderadresse oben links in Textgrösse und schwarz, die
   Empfängeradresse links auf der Höhe des Fenstercouverts (rund 4,6 cm unter
   dem oberen Rand), Datum rechts, fetter Betreff, Grussformel mit Namen – ohne
   Linien und ohne Fusszeile. Dazu kommen die Unterlagen aus dem
   Unterlagenordner (Lebenslauf, Zeugnisse, Diplome). Die Adresse steht schon im
   Feld „An“ des Entwurfs; die Anrede lautet „Sehr geehrter Herr …“ oder
   „Sehr geehrte Frau …“, wenn die Anzeige eine Ansprechperson mit Herr/Frau
   nennt. Fehlt sie im Kontaktfeld, sucht das Programm sie zuerst im
   Anzeigetext und im Text der verlinkten Anzeigenseite (viele Portale betten
   die Anzeige dort ein); Adressen des Portals selbst und technische Kennungen
   bleiben dabei aussen vor. Steht der Kontakt in der Anzeige nur als Bild,
   liest ihn die Texterkennung – aus allen Bildern der Anzeige, nicht nur den
   ersten; Logos, Icons und SVG-Dateien werden an Adresse und Bildbeschreibung
   erkannt und übersprungen. Fehlt danach immer noch etwas, fragt vor dem
   Entwurf ein Fenster nach E-Mail-Adresse und Ansprechperson. Der Entwurf
   landet in Outlook oder Gmail und wird von Hand gesendet.
5. **Versand erkennen.** Nur eine Mail im Ordner „Gesendet“ (die letzten 100)
   gilt als verschickt; dann stehen Versanddatum und Uhrzeit in der
   Bewerbungstabelle. Ein verschwundener Entwurf allein genügt nicht.
6. **Antworten auswerten.** Jede Bewerbung trägt eine einmalige Kennung
   (z. B. `AA-7K4P-Q9XM-3TRZ`), die im HTML-Teil der Mail unsichtbar mitreist
   (weisser Text in Schriftgrösse 0, dazu HTML-Kommentar und Mailkopf
   `X-AutoApplication-Ref`). Das Postfach wird auf Antworten der Firma geprüft –
   zuerst über diese Kennung, dann über die Unterhaltung, die Absenderdomain,
   den Firmennamen oder den Stellentitel. Die KI liest die ganze Antwort und
   unterscheidet **Zusage (Stelle)** – Vertrag oder feste Einstellung – von
   **Einladung (Gespräch)** – Vorstellungsgespräch, Kennenlernen, Terminwunsch.
   Eine Absage archiviert die Bewerbung, Zusage und Einladung erscheinen als
   Hinweis.

   Im Tab **Bewerbungen** stehen drei Tabellen: **Entwurf/Gesendet/Nachgefragt**,
   **Antworten** (Antwort, Einladung, Zusage) und **Absagen und Archiv**. Jede
   Tabelle hat eigene Häkchen für ihre Status; ohne Häkchen ist die Gruppe
   ausgeblendet. Zeilenfarbe: Entwurf weiss, Gesendet grün, Nachgefragt orange,
   Antwort orange, Einladung und Zusage grün, Absage rot, Archiviert grau.
   Doppelklick zeigt je Tabelle die eigene Mail, alle Antworten der Firma in
   einem Fenster oder die Absage. Ein Umschlag in der ersten Spalte markiert
   neue, noch nicht gelesene Antworten: geschlossen und orange pulsierend;
   nach dem Öffnen offen und grau. Bei schmalem Fenster oder grösserer Schrift
   brechen die Häkchenzeilen um, statt rechts abgeschnitten zu werden.
   Der Knopf „E-Mail-Eingang jetzt prüfen“ stösst den Abgleich sofort an, und
   unter „Anschreiben anzeigen“ steht die Kennung der Bewerbung zum Nachschauen;
   im Protokoll steht bei jeder Antwort, wodurch sie zugeordnet wurde.
7. **Nachfassen.** Ohne Antwort nach 14 Tagen zeigt die Übersicht die
   Bewerbung als fällig; auf Klick entsteht die Nachfrage nach Vorlage – einmal
   je Bewerbung. Vor dem Entwurf erscheint dasselbe Prüffenster wie bei der
   Bewerbung: Empfänger, Anrede, Betreff und Text sind änderbar, die
   Rechtschreibprüfung läuft beim Öffnen, und erst mit „Entwurf erstellen“
   entsteht die Mail im Mailkonto. Die Kennung der Bewerbung steht auch in der
   Nachfrage: Erst wenn die Nachfrage im Ordner „Gesendet“ liegt, vermerkt die
   Fünf-Minuten-Prüfung sie als verschickt; im Tab **Bewerbungen** stehen dann
   Versanddatum und Uhrzeit in der Spalte „Fällig“.

## Stellenliste

Der Tab **Stellen** zeigt je Anzeige: ein **F** für ein Bewerbungsformular,
ein **Vorlage**-Feld, Datum, Titel, Ansprechperson, E-Mail, Firma, Ort, Adresse
und PLZ sowie Pensum, Weg, Interesse, Fähigkeit, Treffer und Briefvorlage.
Die Spalte **Briefvorlage** nennt die Vorlage, mit der das Anschreiben
entstehen wird – zum Beispiel «Spedition und Logistik» oder «Allgemeine
Bewerbung»; der Mauszeiger darüber nennt zusätzlich den Status. Die Spalte
**Treffer** zeigt in Prozent, wie viele Ihrer Interessen und Fähigkeiten in der
Anzeige vorkommen: 100 % heisst, dass jedes hinterlegte Stichwort vorkommt,
0 %, dass keines passt; ohne Einträge im Profil steht dort «–». Steht in der
Spalte **Vorlage** «allgemein», passt keine besondere Vorlage – dann wird die
Allgemeine Bewerbung verwendet und der Status ist **Allgemein** statt
**Passend**. Der Statusfilter **Passend** zeigt damit nur Stellen mit mindestens
einem passenden Stichwort; **Allgemein** oder **Alle Status** zeigen die
übrigen. Das **F** steht auch dann, wenn das
Formular nicht auf der Anzeige selbst liegt, sondern auf einer eingebetteten
Seite des Arbeitgebers oder hinter «Jetzt bewerben». Die Suchzeile darüber
findet auch Adresse und Postleitzahl. Die Checkbox **ohne Bewerbungsformulare**
blendet alle Stellen aus, die in der Spalte **F** markiert sind. Die Checkbox
**ohne Jobvermittler** blendet alle Firmen aus der Liste **Einstellungen →
Ostjob → Jobvermittler** aus; der Knopf **Als Jobvermittler eintragen** nimmt
die Firma der markierten oder angehakten Zeilen in diese Liste auf.
**Jetzt Stellen neu suchen** holt die Anzeigen von ostjob.ch; ein
**Doppelklick** auf diesen Knopf prüft zusätzlich **alle** gespeicherten
Stellen ohne Begrenzung – Kontaktdaten, Bewerbungsformular und abgelaufene
Anzeigen, auch bereits geprüfte. Doppelte Einträge werden übersprungen, und der
Zustand der Checkbox bleibt für den nächsten Start erhalten.

- **Ansprechperson mit Anrede.** Nennt die Anzeige „Herr …“ oder „Frau …“, wird
das übernommen. Steht dort nur ein Name, leitet die KI die Anrede aus dem
Vornamen ab, wenn er eindeutig männlich oder weiblich ist (Sandra → Frau,
Michael → Herr); bei unklaren Namen bleibt das Feld leer statt zu raten.
- **E-Mail** ist die Bewerbungsadresse aus der Anzeige.
- **Adresse und PLZ** kommen zuerst aus den Portalangaben (Strasse,
Hausnummer, Postleitzahl der Firma). Fehlen sie dort, liest AutoApplication
Homepage, Impressum und Kontaktseite der Firma und sucht Strasse und
Postleitzahl im geholten Text. Findet sich dort nichts, bleibt die Zeile leer
(„–“): Die KI ist an der Firmenadresse bewusst nicht beteiligt, damit im Brief
nie eine erfundene Adresse steht. Je Firma wird nur einmal gesucht, und
vorhandene Adressen werden bei späteren Läufen nachgetragen.

## Installation

`AutoApplication-1.0.29-Setup.exe` von der
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

Unter **Einstellungen → Ostjob** eintragen:

| Feld | Bedeutung |
| --- | --- |
| Stellen über die API abrufen | Häkchen setzen, sonst wird ostjob.ch nicht abgefragt (Standard: aus) |
| Suchbegriffe | Ein Begriff pro Zeile, z. B. `Spedition`, `Logistik` |
| Ort / placeCode / placeValue | Ortsangabe aus ostjob.ch, z. B. `Balgach 9436 (SG)` / `balgach-sg-9436` |
| Breiten-/Längengrad | Für Umkreis und Arbeitsweg, z. B. `47.4055` / `9.6087` |
| Umkreis der Suche | Umkreis, den das Portal durchsucht |
| Arbeitsweg höchstens | Luftlinie, die eine Anzeige höchstens entfernt sein darf |
| Pensum von/bis | 60–100 lässt 80-%-Stellen zu, 100-%-Stellen fallen bei „bis 90“ heraus |
| Kantone | Leer = alle; sonst z. B. `St. Gallen, Thurgau` |
| Nicht anzeigen | Ausschluss-Stichworte, mit Komma getrennt |

### Profil, Interessen und Fähigkeiten

Unter **Einstellungen → Persönliches** stehen neben den Kontaktdaten zwei Felder für
Stichworte: **Interessen** (wofür Sie sich eher interessieren) und
**Fähigkeiten** (was Sie können). Beide Listen sind unabhängig voneinander –
sie müssen sich nicht decken. Die KI bekommt beides als Zusatz zur
Stellenbeschreibung; in Vorlagen stehen sie als `{interessen}` und
`{faehigkeiten}` bereit.

Das Feld **Werdegang** nimmt die Stationen auf, eine pro Zeile im Muster
`Zeitraum: Funktion, Firma – Aufgaben`. Die KI erhält den Werdegang für den
Mailtext und das Anschreiben und darf Firmen, Jahre und Aufgaben nur von dort
übernehmen. Zwei weitere Felder nennen die Erfahrung in Worten: **Jahre
Erfahrung gesamt** (`{erfahrung}`, Standard `über zwanzig`) und **Jahre in
Spedition/Export** (`{erfahrung_spedition}`, Standard `fast neunzehn`).

### E-Mail-Anbindung

Unter **Einstellungen → E-Mail und Anhänge** wird gewählt, wohin der Entwurf
geht: Outlook, Gmail (IMAP/SMTP) oder „Keine – nur im Programm“. Ohne Anbindung
bleibt der Text in der Bewerbungstabelle und lässt sich von dort kopieren.

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
4. Die **Client-ID** unter **Einstellungen → E-Mail und Anhänge → Outlook** eintragen, Mandant
   `common` lassen, „Anmelden“ wählen und den angezeigten Code auf der
   Microsoft-Seite bestätigen.

Die Anmeldung wird in `outlook_token.json` im Benutzerordner gespeichert (nur
für den eigenen Benutzer lesbar) und automatisch erneuert. „Trennen“ löscht sie.

### Gmail (IMAP/SMTP mit App-Passwort)

Ohne Google-Cloud-Projekt und ohne Microsoft-Konto: AutoApplication meldet sich
mit der Gmail-Adresse und einem App-Passwort an.

1. Im Google-Konto die **2-Faktor-Authentifizierung** aktivieren
   (`myaccount.google.com/security`).
2. Unter **Sicherheit → App-Passwörter** (`myaccount.google.com/apppasswords`)
   ein Passwort für „AutoApplication“ erzeugen und die 16 Zeichen notieren.
3. Unter **Einstellungen → E-Mail und Anhänge → Gmail** Adresse und App-Passwort eintragen und
   **„Verbindung testen“** wählen.
4. Unter **E-Mail-Anbindung** „Gmail (IMAP/SMTP, App-Passwort)“ auswählen.

Entwürfe landen per IMAP in Gmail unter **Entwürfe** (und damit auch in jedem
Mailprogramm, das das Konto abruft); gesendet wird über `smtp.gmail.com:587`.
Der Versand wird im Ordner „Gesendet“ erkannt, Antworten im Posteingang.
Das App-Passwort steht nur in `einstellungen.json` im Benutzerordner.

App-Passwörter gibt es nicht bei Google Advanced Protection oder wenn ein
Workspace-Administrator sie sperrt; dann bleibt nur die Google-OAuth-Anbindung.

### KI (optional) – OpenAI-kompatibel oder Groq

Unter **Einstellungen → KI & Automatisierung** den Anbieter wählen:

| Anbieter | Adresse | Modell (Vorschlag) |
| --- | --- | --- |
| OpenAI oder kompatibel | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Groq | `https://api.groq.com/openai/v1` | `openai/gpt-oss-120b` |

Adresse und Modell füllt die Auswahl automatisch. **«Verbindung prüfen»**
macht zwei Dinge: Es schickt eine winzige Anfrage an das eingestellte Modell
(das sicherste Zeichen, dass die KI antwortet) und trägt die Modelle in die
Auswahlliste ein, die dieser Schlüssel wirklich nutzen kann; das gewünschte
Modell wird dort ausgewählt. Steht das bisherige Modell nicht in der Liste oder
antwortet es nicht, sagt das Programm es im Klartext und lässt die Wahl offen.
Ein eigener Modellname lässt sich weiterhin eintippen.
Schlüssel von Groq unter [console.groq.com](https://console.groq.com/keys)
erstellen. Der Schlüssel lässt sich auch über die Umgebungsvariablen
`AUTOAPPLICATION_AI_KEY`, `OPENAI_API_KEY` oder `GROQ_API_KEY` bereitstellen.

Mit Schlüssel übernimmt die KI vier Aufgaben:

| Aufgabe | Ergebnis |
| --- | --- |
| Anzeige auslesen | sauberer Titel (männliche Form, ohne `(m/w/d)`, `(gn*)`, IDs), bereinigte Beschreibung, Bewerbungsadresse |
| Stichworte | Grundlage für die Wahl der Vorlage |
| Mailtext | Betreff und Text des Entwurfs, auf Stelle und Profil zugeschnitten |
| Anschreiben | PDF im Ordner `anschreiben`, wird als erster Anhang mitgeschickt |

Ohne KI bleibt alles nutzbar: Titel und Beschreibung werden lokal bereinigt,
der Mailtext kommt aus der Vorlage und als Anschreiben wird derselbe Text als
PDF verwendet. Abschalten lässt sich der PDF-Anhang unter
**Einstellungen → E-Mail und Anhänge → Unterlagen**.

Ohne KI bleibt alles nutzbar: die Stichworte kommen dann aus den
Portalangaben und dem Stichwortverzeichnis der Vorlagen, die Antwortauswertung
arbeitet mit typischen Formulierungen.

### Unterlagen

Unter **Einstellungen → E-Mail und Anhänge → Unterlagen** den Ordner mit Lebenslauf, Zeugnissen und
Diplomen wählen. Alle PDF-, Word- und Bilddateien darin werden angehängt –
Dateien mit „Lebenslauf“, „Zeugnis“ oder „Diplom“ im Pfad zuerst. Die
Gesamtgrösse ist begrenzt (Standard 20 MB); einzelne Anhänge über 3 MB lässt
Microsoft Graph nicht als einfachen Anhang zu und werden ausgelassen.

Die Einstellungen haben vier Reiter: **Persönliches**, **Ostjob**,
**E-Mail und Anhänge (Unterlagen)** sowie **KI & Automatisierung**.

### Anschreiben-Vorlage

Das PDF-Anschreiben entsteht aus einer Textvorlage im Ordner `briefvorlagen`
im Benutzerordner. Unter **Einstellungen → E-Mail und Anhänge → Anschreiben-Vorlage**
steht jede `.txt`-Datei dieses Ordners zur Auswahl; „Ordner öffnen“ zeigt den
Ordner, „Beispielvorlage anlegen“ schreibt die mitgelieferte `standard.txt`.

Die Vorlage ist der ganze Brief – Absenderblock, Empfänger, Ort und Datum,
Betreff, Text, Grussformel und Name. Leerzeilen bestimmen die Abstände,
Zeilen mit `#` am Anfang sind nur Notizen. Platzhalter werden beim Erzeugen
ersetzt: `{vorname}`, `{nachname}`, `{name}`, `{strasse}`, `{plz}`,
`{wohnort}`, `{telefon}`, `{email}`, `{firma}`, `{firma_strasse}`,
`{firma_plz_ort}` (z. B. „9436 Balgach“), `{ort}`, `{titel}`, `{betreff}`,
`{datum}`, `{ort_datum}`, `{verfuegbar}`, `{erfahrung}`,
`{erfahrung_spedition}` und `{text}` (der ganze Brieftext ab der Anrede, ohne
Schlussformel). Mit `{fett}` am Zeilenanfang wird die Zeile fett, mit
`{rechts}` am Zeilenanfang rechtsbündig gesetzt – so steht das Datum rechts.
Steht `{rechts}` **mitten** in der Zeile, bleibt der vordere Teil links und der
Rest steht rechts, etwa `{firma_plz_ort} {rechts} {ort_datum}`: PLZ und Ort
links, Ort und Datum rechts auf derselben Zeile.

Die Mail-Vorschau vor dem Entwurf zeigt unter **„Anschrift im Anschreiben“**
den Empfängerblock so, wie er im PDF steht: Firma, Strasse, PLZ und Ort.
Fehlt die Adresse, wird sie vorher noch gesucht (Portal, dann Firmenwebsite).
Enthält die gewählte Vorlage `{firma_strasse}` oder `{firma_plz_ort}` nicht,
warnt die Vorschau, dass diese Angaben im PDF fehlen. Steht der Ort schon in
`{firma_plz_ort}`, fällt eine zusätzliche `{ort}`-Zeile weg – die Stadt steht
nie doppelt im Brief.

**„Vorschau als PDF“** erzeugt ein PDF, in dem jeder Platzhalter selbst an
seinem Platz steht. Damit lässt sich die Vorlage gestalten, ohne ein
Anschreiben abzuwarten; die Änderung an der `.txt`-Datei gilt ab dem nächsten
Brief.

## Vorlagen

Unter **Vorlagen** lassen sich Name, Stichworte, Betreff und Text bearbeiten,
neue Vorlagen anlegen und die Standardvorlagen wiederherstellen. Eine Vorlage
gilt für Nachfragen, wenn das Häkchen gesetzt ist. Das Häkchen **Allgemeine
Vorlage** bestimmt die Auffangvorlage: Sie wird gewählt, wenn keine oder zu
wenige Stichworte einer anderen Vorlage passen. Es gilt immer nur eine.

Mitgeliefert sind 29 Bewerbungsvorlagen, eine allgemeine Auffangvorlage und
eine Nachfrage-Vorlage:

| Vorlage | Stichworte (Auszug) |
| --- | --- |
| Spedition und Logistik | Spedition, Disposition, Transport, Fracht, Luftfracht, Export, Zoll, ERP |
| Export, Zoll und Aussenhandel | Exportabwicklung, Zolldeklaration, Exportkontrolle, Aussenhandel, Transit, Akkreditiv |
| Lager und Kommissionierung | Kommissionierung, Warenannahme, Warenausgang, Stapler, Inventur, Verpackung |
| Technischer Kundendienst und Kassensysteme | Kassensystem, POS, Zahlungsterminal, Servicetechniker, Inbetriebnahme, Fernwartung |
| IT-Support und Anwenderbetreuung | Helpdesk, First Level, Ticketsystem, Anwenderbetreuung, Microsoft 365, Netzwerk |
| Kundenberatung und Verkaufsinnendienst | Kundenberatung, Verkaufsinnendienst, Auftragsbearbeitung, Offerte, CRM |
| Administration und Sachbearbeitung | Sachbearbeitung, Administration, Verwaltung, Büro, Backoffice, Kundendienst |
| Produktion und Fertigung | Produktion, Fertigung, Serienfertigung, Fliessband, Schicht, Werkstatt |
| Montage und Anlagenbau | Montage, Monteur, Anlagenbau, Baugruppen, Montageanleitung, Demontage |
| Maschinen- und Anlagenbedienung | Maschinenbediener, Anlagenbediener, Maschinenführer, Einrichten, Rüsten |
| Qualitätssicherung und Prüfung | Qualitätssicherung, Endkontrolle, Messmittel, Audit, Prüfprotokoll |
| Einkauf und Beschaffung | Einkauf, Beschaffung, Lieferant, Bestellwesen, Offertvergleich |
| Buchhaltung und Finanzen | Buchhaltung, Debitoren, Kreditoren, Rechnungswesen, Jahresabschluss |
| Personal und HR-Administration | Personalwesen, Rekrutierung, Personaldossier, Lohnadministration |
| Empfang, Sekretariat und Telefon | Empfang, Rezeption, Sekretariat, Telefondienst, Terminplanung |
| Kundenservice und Beratung am Telefon | Kundenservice, Callcenter, Kundenanfragen, Reklamation, Beratung |
| Fahrdienst und Kurier | Chauffeur, Fahrer, Kurier, Lieferfahrer, Zustellung, Touren |
| Handwerk und Gebäudetechnik | Handwerk, Gebäudetechnik, Instandhaltung, Reparatur, Hauswart |
| Bau und Baunebengewerbe | Baustelle, Bauarbeiter, Tiefbau, Hochbau, Ausbau, Schalung |
| Reinigung und Hausdienst | Reinigung, Unterhaltsreinigung, Hausdienst, Hygiene, Grundreinigung |
| Sicherheit und Pfortendienst | Sicherheitsdienst, Pforte, Wachdienst, Zutrittskontrolle, Überwachung |
| Gastronomie und Service | Gastronomie, Restaurant, Servicemitarbeiter, Küche, Bankett |
| Hotel und Rezeption | Hotel, Hotellerie, Rezeption, Housekeeping, Reservation |
| Landwirtschaft und Gartenbau | Landwirtschaft, Gartenbau, Gärtner, Pflanzen, Grünpflege |
| Gesundheit und Pflege | Pflege, Pflegehelfer, Senioren, Spital, Arztpraxis, Patienten |
| Soziales und Betreuung | Sozialbegleitung, Betreuung, Integration, Kinder, Wohnheim |
| Bildung und Lernbegleitung | Bildung, Schule, Lernbegleitung, Unterricht, Kursleitung |
| Ausbildung und Lehrstelle | Lehrstelle, Lehrling, Berufslehre, Ausbildungsplatz, Umschulung |
| Marketing und Kommunikation | Marketing, Kommunikation, Social Media, Kampagne, Newsletter |
| Allgemeine Bewerbung | keine – greift, wenn keine andere Vorlage passt |

Die Texte sind auf den bisherigen Werdegang zugeschnitten (Spedition und
Export, Kassensysteme und Technik, Kundenkontakt, Administration) und nennen
konkrete Aufgaben statt allgemeiner Sätze. Wo eine Branche neu ist, sagt die
Vorlage offen, was vorhanden ist, und bietet an, eine geforderte Ausbildung zu
machen. Beim ersten Start nach einem Update werden mitgelieferte Vorlagen
nachgezogen und neue ergänzt; eigene Vorlagen und selbst bearbeitete
Standardvorlagen bleiben unverändert.

Platzhalter in Betreff und Text:

| Platzhalter | Inhalt |
| --- | --- |
| `{anrede}` | „Sehr geehrter Herr Müller“, „Sehr geehrte Frau Meier“ oder „Sehr geehrte Damen und Herren“ |
| `{ansprechperson}` | Ansprechperson aus der Anzeige (z. B. `Frau Meier`) oder leer |
| `{titel}` | Stellentitel |
| `{firma}` | Firmenname |
| `{ort}` | Arbeitsort |
| `{pensum}` | Pensum aus der Anzeige |
| `{stellen_id}` | Inseratsnummer |
| `{datum}` | heutiges Datum |
| `{vorname}`, `{nachname}`, `{strasse}`, `{plz}`, `{wohnort}`, `{telefon}`, `{email}` | Angaben aus dem Profil |
| `{erfahrung}` | Jahre Erfahrung aus dem Profil (Standard: `über zwanzig`) |
| `{verfuegbar}` | Verfügbarkeit aus dem Profil |
| `{interessen}`, `{faehigkeiten}` | Stichworte aus dem Profil |
| `{bewerbungsdatum}`, `{tage}` | nur in der Nachfrage-Vorlage |

## Automatik

- **Täglicher Lauf** zur eingestellten Uhrzeit: Stellen suchen, Versand
  prüfen, Antworten auswerten. Entwürfe und Nachfragen entstehen nur auf Klick.
- **Beim Start** läuft der Tageslauf einmal, wenn er heute noch nicht lief.
- **Postfach prüfen** und **Nachfragen vorbereiten** gehen auch von Hand. Die
  Statusleiste nennt dabei die Schritte: «Prüfe gesendete E-Mails …», «Prüfe
  Entwürfe …» und «Prüfe Posteingang …».

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
| `einstellungen.json` | Profil, Suche, KI, E-Mail, Automatik |
| `daten.db` | Stellen, Bewerbungen, Antworten (mit vollem Text und Gelesen-Kennzeichen), Protokoll (SQLite) |
| `vorlagen.json` | Vorlagen |
| `anschreiben/` | erzeugte Anschreiben als PDF |
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

Der Selbsttest meldet auch die Texterkennung, z. B.
`OCR: Windows-Texterkennung (winrt) liest das Testbild, Adresse anna.muster@example.ch erkannt.`
Fehlt sie ganz, steht dort `keine Windows-Texterkennung: Kontakte aus Bildern werden
übersprungen.` – dann fragt das Programm die Angaben wie bisher von Hand ab. Ist eine
Texterkennung vorhanden, das Testbild aber nicht lesbar, endet der Selbsttest mit Code 4.
Derselbe Satz steht beim Start und im Tageslauf im Protokoll (Art `ocr`, nur bei Änderung).

Aufbau:

```
src/autoapplication/
  app.py              Start, Selbsttest, Tageslauf ohne Fenster
  core/               Konfiguration, Ablage, ostjob.ch, KI, Vorlagen, Outlook, Gmail (IMAP), Ablauf, Updater
  data/templates.json Standardvorlagen
  data/ocr-test.png  Testbild für die Diagnose der Texterkennung
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
  nichts getan. Solange die API ausgeschaltet ist, wird sie gar nicht erst
  abgefragt.
- Nicht jede Anzeige nennt eine E-Mail-Adresse. Dann bleibt der Entwurf ohne
  Empfänger stehen und die Adresse wird von Hand ergänzt (oder die
  Online-Bewerbung im Feld „Stelle öffnen“ benutzt).
- Die Antwortauswertung ist eine Einordnung, keine Rechtsauskunft: Absagen,
  Einladungen und Zusagen werden erkannt, Sonderfälle bleiben als „Antwort“
  stehen. Ein Gesprächstermin gilt auch dann als Einladung, wenn die Mail das
  Wort «Zusage» enthält («Zusage zum Vorstellungsgespräch»).
- Die Kennung reist im zitierten Mailtext mit. Antwortet jemand in reinem Text
  und ohne Zitat der ursprünglichen Mail, fehlt sie – dann greifen wieder
  Unterhaltung, Absenderdomain, Firmenname und Stellentitel.
