"""
check_mensa.py - Taegliche Glutenfrei-Benachrichtigung fuer die Mensa am Schloss
und das EO (Bar & Lounge) in Mannheim.

Was das Skript macht:
  1. Holt die heutigen Gerichte der Mensa am Schloss von der OpenMensa-API.
  2. Liest den "Mittagstisch" von der EO-Website (eo-mannheim.de), weil das EO
     nicht bei OpenMensa gelistet ist.
  3. Filtert Gerichte heraus, die laut Kennzeichnung Gluten enthalten.
  4. Schickt das Ergebnis als Push-Nachricht ueber ntfy.sh auf dein Handy.

Benutzung:
  python3 check_mensa.py --dry-run      -> Nachricht nur anzeigen, nichts senden
  NTFY_TOPIC=dein-topic python3 check_mensa.py   -> wirklich senden

Nur Python-Standardbibliothek, es muss nichts installiert werden.
"""

import datetime
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# EINSTELLUNGEN - hier kannst du alles anpassen
# ---------------------------------------------------------------------------

# Mensen bei OpenMensa: Anzeigename -> Canteen-ID.
# IDs findest du z. B. unter https://openmensa.org/api/v2/canteens/285
OPENMENSA_CANTEENS = {
    "Mensa am Schloss": 285,
    "greenes²": 1718,  # im Gebäude der Mensa am Schloss
}

# EO Bar & Lounge: nicht bei OpenMensa, daher lesen wir die Website aus.
# Auf False setzen, wenn du das EO nicht mehr willst.
CHECK_EO = True
EO_URL = "https://eo-mannheim.de/"

# Woerter in den OpenMensa-"notes", die Gluten bedeuten.
# Vergleich ohne Gross-/Kleinschreibung und als Teilwort
# ("weizen" trifft also auch "Weizenmehl" - und leider auch "Buchweizen",
# das eigentlich glutenfrei ist. Lieber zu vorsichtig als zu lax.)
GLUTEN_KEYWORDS = [
    "glutenhaltig",   # "Glutenhaltiges Getreide"
    "gluten",
    "weizen",
    "gerste",
    "roggen",
    "hafer",
    "dinkel",
    "grünkern",
    "kamut",
    "emmer",
    "einkorn",
]

# Allergen-Kuerzel auf der EO-Website, die Gluten bedeuten.
# Legende laut EO-Seite: GlW=Weizen, GlD=Dinkel, GlR=Roggen, GlH=Hafer,
# GIG/GlG=Gerste (auf der Seite steht "GIG" mit grossem i), Gl=Gluten allgemein.
# Zusaetzlich gilt JEDES Kuerzel, das mit "Gl" beginnt, als glutenhaltig.
EO_GLUTEN_CODES = ["Gl", "GlW", "GlD", "GlR", "GlH", "GlG", "GIG"]

# Warnwoerter im NAMEN des Gerichts. Die Kennzeichnung ist nicht immer
# vollstaendig (z. B. "Backhendel" ohne Gluten-Kuerzel). Findet sich eines
# dieser Woerter, wird das Gericht mit einer Warnung angezeigt statt als "ok".
NAME_WARNING_WORDS = [
    "panier", "paniert", "backhendel", "backfisch", "schnitzel", "cordon",
    "gnocchi", "spätzle", "knödel", "maultasche", "nudel", "pasta",
    "spaghetti", "lasagne", "ravioli", "tortellini", "brot", "brötchen",
    "burger", "baguette", "ciabatta", "pizza", "flammkuchen", "wrap",
    "tortilla", "couscous", "bulgur", "seitan", "crouton", "kuchen",
    "strudel", "teig", "mehlschwitze", "sojasauce", "sojasoße",
]

DISCLAIMER = "Angaben laut Speiseplan-Kennzeichnung, keine Garantie für Kreuzkontamination."

OPENMENSA_API = "https://openmensa.org/api/v2"
NTFY_SERVER = "https://ntfy.sh"
TIMEZONE = ZoneInfo("Europe/Berlin")

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def http_get(url):
    """Laedt eine URL und gibt den Text zurueck."""
    request = urllib.request.Request(url, headers={"User-Agent": "mensa-glutenfrei-check/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def clean_name(text):
    """Raeumt Gerichtnamen auf: doppelte Leerzeichen, ' ,' -> ','."""
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace(" ,", ",")
    return text.strip(" ,")


def name_warning(name):
    """Gibt das erste Warnwort zurueck, das im Namen vorkommt, sonst None."""
    lower = name.lower()
    for word in NAME_WARNING_WORDS:
        if word in lower:
            return word
    return None


# ---------------------------------------------------------------------------
# Datenquelle 1: OpenMensa
# ---------------------------------------------------------------------------


def fetch_openmensa(canteen_id, day):
    """
    Holt die Gerichte einer Mensa fuer einen Tag.
    Rueckgabe: (status, gerichte)
      status ist "ok", "closed" oder "no_data"
      gerichte ist eine Liste von {"name", "category", "has_gluten"}
    """
    date_str = day.isoformat()
    try:
        day_info = json.loads(http_get(f"{OPENMENSA_API}/canteens/{canteen_id}/days/{date_str}"))
    except urllib.error.HTTPError as error:
        if error.code == 404:  # OpenMensa kennt diesen Tag nicht
            return "no_data", []
        raise

    if day_info.get("closed"):
        return "closed", []

    meals = json.loads(http_get(f"{OPENMENSA_API}/canteens/{canteen_id}/days/{date_str}/meals"))
    result = []
    for meal in meals:
        notes_text = " ".join(meal.get("notes", [])).lower()
        has_gluten = any(keyword in notes_text for keyword in GLUTEN_KEYWORDS)
        result.append({
            "name": clean_name(meal["name"]),
            "category": meal.get("category", ""),
            "has_gluten": has_gluten,
        })
    return "ok", result


# ---------------------------------------------------------------------------
# Datenquelle 2: EO-Website (Scraping)
# ---------------------------------------------------------------------------


def fetch_eo():
    """
    Liest die Tabelle "Mittagstisch" von eo-mannheim.de.
    Rueckgabe: (status, gerichte), status ist "ok" oder "parse_error".

    Achtung: Auf der Seite steht kein Datum. Wir koennen also nicht pruefen,
    ob der Plan wirklich von heute ist.
    """
    page = http_get(EO_URL)

    # Nur den Abschnitt zwischen "Mittagstisch" und "Zum Abend" nehmen.
    section = re.search(r'id="mittagstisch"(.*?)id="zumabend"', page, re.S)
    if not section:
        return "parse_error", []

    # Jede Tabellenzeile: <td class="title">...</td> <td class="description">...</td>
    rows = re.findall(
        r'<td class="title">(.*?)</td>\s*<td class="description">(.*?)</td>',
        section.group(1),
        re.S,
    )
    if not rows:
        return "parse_error", []

    result = []
    for title_html, description_html in rows:
        # Alle Allergen-Kuerzel stehen in <sup>(GlW,Mi,...)</sup>
        codes = []
        for sup in re.findall(r"<sup>\((.*?)\)</sup>", description_html):
            codes += [code.strip() for code in sup.split(",")]
        has_gluten = any(code in EO_GLUTEN_CODES or code.startswith("Gl") for code in codes)

        # Kuerzel entfernen, HTML-Tags entfernen -> lesbarer Name
        name = re.sub(r"<sup>.*?</sup>", "", description_html)
        name = html.unescape(re.sub(r"<[^>]+>", "", name))
        category = html.unescape(re.sub(r"<[^>]+>", "", title_html)).strip()
        category = category.replace("EO Mittagstisch", "").strip()

        result.append({
            "name": clean_name(name),
            "category": category,
            "has_gluten": has_gluten,
        })
    return "ok", result


# ---------------------------------------------------------------------------
# Nachricht bauen und senden
# ---------------------------------------------------------------------------


def format_section(title, status, meals):
    """Baut den Textblock fuer eine Mensa."""
    lines = [f"🏫 {title}"]

    if status == "closed":
        lines.append("Mensa heute geschlossen.")
        return lines
    if status == "no_data":
        lines.append("Keine Daten für heute (evtl. geschlossen).")
        return lines
    if status == "parse_error":
        lines.append("❗ Speiseplan konnte nicht gelesen werden (Website geändert?).")
        return lines
    if status == "error":
        lines.append("❗ Fehler beim Abrufen der Daten.")
        return lines

    candidates = [meal for meal in meals if not meal["has_gluten"]]
    if not candidates:
        lines.append("Heute nichts Glutenfreies gefunden.")
        return lines

    for meal in candidates:
        label = f"{meal['name']} ({meal['category']})" if meal["category"] else meal["name"]
        warning = name_warning(meal["name"])
        if warning:
            lines.append(f"⚠️ {label}. Nicht als glutenhaltig gekennzeichnet, aber der Name enthält „{warning}“, also nachfragen.")
        else:
            lines.append(f"✅ {label}")
    return lines


def build_message(today):
    """Fragt alle Quellen ab und baut die komplette Nachricht."""
    blocks = []

    for name, canteen_id in OPENMENSA_CANTEENS.items():
        try:
            status, meals = fetch_openmensa(canteen_id, today)
        except Exception as error:  # Netzwerkfehler usw. -> trotzdem Nachricht senden
            print(f"Fehler bei {name}: {error}", file=sys.stderr)
            status, meals = "error", []
        blocks.append(format_section(name, status, meals))

    if CHECK_EO:
        try:
            status, meals = fetch_eo()
        except Exception as error:
            print(f"Fehler beim EO: {error}", file=sys.stderr)
            status, meals = "error", []
        blocks.append(format_section("EO Bar & Lounge", status, meals))

    body = "\n\n".join("\n".join(block) for block in blocks)
    body += f"\n\nℹ️ {DISCLAIMER}"
    title = f"Glutenfrei heute ({today.strftime('%d.%m.')})"
    return title, body


def send_ntfy(topic, title, body):
    """Schickt die Nachricht an ntfy.sh (als JSON, damit Umlaute funktionieren)."""
    payload = json.dumps({
        "topic": topic,
        "title": title,
        "message": body,
        "tags": ["fork_and_knife"],
    }).encode("utf-8")
    request = urllib.request.Request(
        NTFY_SERVER,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        print(f"Gesendet an ntfy (HTTP {response.status}).")


def main():
    dry_run = "--dry-run" in sys.argv
    today = datetime.datetime.now(TIMEZONE).date()

    title, body = build_message(today)
    print(title)
    print("-" * len(title))
    print(body)
    print()

    if dry_run:
        print("(--dry-run: nichts gesendet)")
        return

    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        sys.exit("Fehler: Umgebungsvariable NTFY_TOPIC ist nicht gesetzt.")
    send_ntfy(topic, title, body)


if __name__ == "__main__":
    main()
