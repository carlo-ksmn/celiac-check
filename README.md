# Glutenfrei-Check Mensa Mannheim

Schickt werktags morgens eine Push-Nachricht aufs Handy. Darin steht, welche Gerichte in der **Mensa am Schloss**, im **greenes²** und im **EO Bar & Lounge** laut Speiseplan kein glutenhaltiges Getreide enthalten.

> Angaben laut Speiseplan-Kennzeichnung, keine Garantie für Kreuzkontamination. Das ist eine Convenience-Info und keine medizinische Sicherheit.

## Woher die Daten kommen

| Ort | Quelle | Hinweis |
|---|---|---|
| Mensa am Schloss | [OpenMensa-API](https://openmensa.org/api/v2/canteens/285), ID **285** | Allergene als Text in `notes` |
| greenes² | [OpenMensa-API](https://openmensa.org/api/v2/canteens/1718), ID **1718** | wie Mensa am Schloss |
| EO Bar & Lounge | Website [eo-mannheim.de](https://eo-mannheim.de/#mittagstisch) (Scraping) | Nicht bei OpenMensa gelistet. Auf der Seite steht kein Datum. Wenn sich das Seitendesign ändert, meldet die Nachricht „konnte nicht gelesen werden“. |

**Bekannte Lücke:** Die Kennzeichnung ist nicht immer vollständig. Beispiele: „Backhendel“ ohne Gluten-Kürzel, „Gnocchi“ ohne Weizen. Solche Gerichte zeigt das Skript mit ⚠️ an. Dafür sucht es nach Warnwörtern im Gerichtnamen (`NAME_WARNING_WORDS`).

## Lokal testen

Im Terminal in diesen Ordner wechseln und ausführen:

```bash
python3 check_mensa.py --dry-run
```

Damit wird die Nachricht nur angezeigt und nicht gesendet. Zum echten Senden an dein Handy:

```bash
NTFY_TOPIC=dein-topic-name python3 check_mensa.py
```

## Was du ändern kannst

Alle Einstellungen stehen oben in `check_mensa.py`:

- **Mensen:** `OPENMENSA_CANTEENS`. Um eine weitere Mensa hinzuzufügen, suchst du ihre ID auf openmensa.org und ergänzt eine Zeile wie `"Name": ID,`. Mit `CHECK_EO = False` schaltest du das EO ab.
- **Gluten-Wörter:** `GLUTEN_KEYWORDS` (für OpenMensa) und `EO_GLUTEN_CODES` (Kürzel auf der EO-Seite).
- **Warnwörter im Namen:** `NAME_WARNING_WORDS`
- **Topic-Name:** Der steht nicht im Code, sondern als GitHub Secret `NTFY_TOPIC` (Repo → Settings → Secrets and variables → Actions). Dort kannst du ihn ändern. Danach auch in der ntfy-App das neue Topic abonnieren.
- **Uhrzeit:** in `.github/workflows/mensa.yml` die Zeile `cron: "5 7 * * 1-5"`. Achtung, das ist **UTC**: 07:05 UTC ist im Sommer 09:05 und im Winter 08:05 deutscher Zeit.

## ntfy-App einrichten

1. App „ntfy“ installieren (iOS App Store oder Google Play, kostenlos).
2. In der App auf **+** tippen, Topic-Name eingeben und abonnieren (Server: `ntfy.sh`).
3. Wer den Topic-Namen kennt, kann die Nachrichten mitlesen. Deshalb sollte der Name lang und zufällig sein.

## Wichtig: GitHub pausiert inaktive Workflows

In **öffentlichen** Repos schaltet GitHub geplante Workflows nach **60 Tagen ohne Commit** ab. Dann bekommst du eine E-Mail. Du kannst den Workflow unter *Actions → Glutenfrei-Check Mensa → Enable workflow* wieder einschalten.
