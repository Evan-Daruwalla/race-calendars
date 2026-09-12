"""Build one subscribable .ics calendar per racing series.

Sources:
  - sportstimes/f1 (MIT) JSON for F1, Formula E, IndyCar and MotoGP: every session, in UTC.
  - data/<series>.toml, entered by hand from official series pages (a source URL on every
    event), for series sportstimes doesn't cover and for announced seasons it hasn't added yet.
Output: docs/<series>.ics, docs/manifest.json and docs/index.html (GitHub Pages serves /docs).
Stdlib only; Python 3.11+ (tomllib).
"""
import datetime as dt
import json
import re
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs"
RAW = "https://raw.githubusercontent.com/sportstimes/f1/main/_db/{site}/{file}"
REPO = "https://github.com/sportstimes/f1"
DTSTAMP = "20260910T000000Z"  # fixed, so unchanged data rebuilds byte-identical (no daily commit churn)
PAGES = "evan-daruwalla.github.io/race-calendars"

# key: (calendar name, summary prefix, sportstimes site or None, suffix added to sportstimes race names)
SERIES = {
    "f1": ("Formula 1", "F1", "f1", " Grand Prix"),
    "formula-e": ("Formula E", "FE", "fe", ""),
    "indycar": ("IndyCar Series", "IndyCar", "indycar", ""),
    "motogp": ("MotoGP", "MotoGP", "motogp", " Grand Prix"),
    "nascar": ("NASCAR Cup Series", "NASCAR", None, ""),
    "wec": ("FIA World Endurance Championship", "WEC", None, ""),
    "imsa": ("IMSA WeatherTech SportsCar Championship", "IMSA", None, ""),
    "wrc": ("FIA World Rally Championship", "WRC", None, ""),
}
WANT = re.compile(r"practice|^fp\d$|qualif|sprint|race|^gp$", re.I)  # practice + qualifying + races
SKIP = re.compile(r"warmup|other", re.I)
LABELS = {"gp": "Race", "fp1": "Practice 1", "fp2": "Practice 2", "fp3": "Practice 3",
          "sprintQualifying": "Sprint Qualifying", "qualifying1": "Qualifying 1",
          "qualifying2": "Qualifying 2", "FinalPractice": "Final Practice"}
MOTOGP_LABELS = {"fp1": "Free Practice 1", "fp2": "Free Practice 2"}


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "race-calendars-build"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def label(site, key):
    if site == "motogp" and key in MOTOGP_LABELS:
        return MOTOGP_LABELS[key]
    return LABELS.get(key) or re.sub(r"(?<=[a-z])(?=[A-Z0-9])", " ", key).title()


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def ev(uid, summary, start, end, location, description, url, allday=False):
    return {"uid": uid, "summary": summary, "start": start, "end": end, "location": location or "",
            "description": description, "url": url, "allday": allday}


def sportstimes(key, prefix, site, suffix, this_year):
    """Every wanted session for current and future seasons. Returns (events, all seasons sportstimes has)."""
    cfg = fetch_json(RAW.format(site=site, file="config.json"))
    lengths = cfg.get("sessionLengths", {})
    have = set(cfg.get("availableYears", []))
    out = []
    for year in sorted(y for y in have if y >= this_year):
        for race in fetch_json(RAW.format(site=site, file=f"{year}.json"))["races"]:
            title = race["name"] + suffix + (" (TBC)" if race.get("tbc") else "")
            for skey, iso in (race.get("sessions") or {}).items():
                if not iso or SKIP.search(skey) or not WANT.search(skey):
                    continue
                start = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
                end = start + dt.timedelta(minutes=lengths.get(skey, 60))
                # round in the UID: double-headers repeat the same race name/slug within a season
                out.append(ev(f"{key}-{year}-r{race.get('round', 0)}-{race.get('slug') or slug(race['name'])}-{slug(skey)}",
                              f"{prefix}: {title} - {label(site, skey)}", start, end, race.get("location"),
                              f"Source: sportstimes/f1 (MIT), {REPO} . End time is the typical session length.",
                              REPO))
    return out, have


def handfile(key, prefix, skip_seasons):
    """Events from data/<key>.toml. Timed sessions need an explicit UTC offset; no sessions = all-day event."""
    path = ROOT / "data" / f"{key}.toml"
    if not path.exists():
        return []
    doc = tomllib.loads(path.read_text(encoding="utf-8"))
    default_min = doc.get("default_minutes", {})
    out = []
    for e in doc.get("event", []):
        if e["season"] in skip_seasons:  # sportstimes has this season now: its data wins
            continue
        base = f"{key}-{e['season']}-{slug(e['name'])}"
        url, checked = e.get("source", doc.get("source")), e.get("checked", doc.get("checked"))
        first, last = e.get("start_date", e.get("date")), e.get("end_date", e.get("date"))
        src = f"Source: {url} (checked {checked})."
        sessions = e.get("session", [])
        for s in sessions:
            start = s["start"]
            if not isinstance(start, dt.datetime) or start.tzinfo is None:
                raise ValueError(f"{path.name}: '{e['name']} / {s['name']}' needs a start with a UTC offset")
            start = start.astimezone(dt.timezone.utc)
            kind = "race" if re.search(r"race|hours|km|500|400|300", s["name"], re.I) else "session"
            minutes = s.get("minutes") or default_min.get(kind, 60)
            note = "" if "minutes" in s else " End time is an estimate."
            out.append(ev(f"{base}-{slug(s['name'])}", f"{prefix}: {e['name']} - {s['name']}", start,
                          start + dt.timedelta(minutes=minutes), e.get("location"), src + note, url))
        if not sessions:
            out.append(ev(base, f"{prefix}: {e['name']} (times TBA)", first, last + dt.timedelta(days=1),
                          e.get("location"), src + " Session times not published yet.", url, allday=True))
    return out


def esc(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):
    """RFC 5545: lines of at most 75 octets; continuation lines start with one space. Never splits a UTF-8 char."""
    out, cur, limit = [], b"", 75
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > limit:
            out.append(cur)
            cur, limit = b" ", 75
        cur += b
    out.append(cur)
    return b"\r\n".join(out)


def stamp(x, allday):
    return x.strftime("%Y%m%d") if allday else x.strftime("%Y%m%dT%H%M%SZ")


def ics(key, name, events):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//race-calendars//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{esc(name)}",
             f"X-WR-CALDESC:{esc(name + ' - practice, qualifying and races. Times in UTC; your calendar app shows them in your time zone.')}",
             "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
    for e in sorted(events, key=lambda e: (str(e["start"]), e["uid"])):
        d = ";VALUE=DATE" if e["allday"] else ""
        lines += ["BEGIN:VEVENT", f"UID:{e['uid']}@race-calendars", f"DTSTAMP:{DTSTAMP}",
                  f"DTSTART{d}:{stamp(e['start'], e['allday'])}", f"DTEND{d}:{stamp(e['end'], e['allday'])}",
                  f"SUMMARY:{esc(e['summary'])}", f"LOCATION:{esc(e['location'])}",
                  f"DESCRIPTION:{esc(e['description'])}", f"URL:{e['url']}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return b"\r\n".join(fold(l) for l in lines) + b"\r\n"


def main():
    this_year = dt.datetime.now(dt.timezone.utc).year
    OUT.mkdir(exist_ok=True)
    manifest = {}
    for key, (name, prefix, site, suffix) in SERIES.items():
        upstream, have = sportstimes(key, prefix, site, suffix, this_year) if site else ([], set())
        hand = handfile(key, prefix, have)
        events = upstream + hand
        (OUT / f"{key}.ics").write_bytes(ics(key, name, events))
        manifest[key] = {"name": name, "events": len(events), "from_sportstimes": len(upstream),
                         "from_data_file": len(hand), "all_day": sum(e["allday"] for e in events),
                         "sportstimes_seasons": sorted(have)}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    rows = "\n".join(f'<li><b>{v["name"]}</b>: <a href="webcal://{PAGES}/{k}.ics">subscribe</a> '
                     f'&middot; <a href="https://{PAGES}/{k}.ics">https link</a> ({v["events"]} events)</li>'
                     for k, v in manifest.items())
    (OUT / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>race-calendars</title>"
        "<h1>Race calendars</h1><p>One subscribable calendar per series: practice, qualifying and races. "
        "Times are UTC in the files; calendar apps show them in your own time zone.</p>"
        f"<ul>\n{rows}\n</ul><p>Source and details: "
        '<a href="https://github.com/Evan-Daruwalla/race-calendars">github.com/Evan-Daruwalla/race-calendars</a></p>\n',
        encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    for k, v in manifest.items():
        print(f"{k:10} events={v['events']:4} sportstimes={v['from_sportstimes']:4} "
              f"data_file={v['from_data_file']:3} all_day={v['all_day']:3} seasons={v['sportstimes_seasons']}")


if __name__ == "__main__":
    main()
