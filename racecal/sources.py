"""Where schedule data comes from, and how a session becomes an anchor or a block.

Two sources, deliberately kept apart:
  UPSTREAM  - sportstimes/f1 JSON (MIT). Legitimately changes between builds (it gained a
              MotoGP session on 2026-09-11), so it gets NO frozen checksum: asserting a count
              against a live feed would fail the daily job every time the feed is corrected.
  HAND      - data/<series>.toml, transcribed BY HAND from official series pages, every event
              carrying its source URL and the date it was read. Nothing infers or estimates a
              date here. This data IS frozen, so it gets a hand-counted `expected_events`
              checksum: a transcription slip must fail loud rather than quietly reshape a
              schedule. The two checks answer different questions and must not be merged.
"""
import datetime as dt
import json
import re
import tomllib
import urllib.request
from pathlib import Path

from .ics import ANCHOR, BLOCK, event

ROOT = Path(__file__).resolve().parent.parent
RAW = "https://raw.githubusercontent.com/sportstimes/f1/main/_db/{site}/{file}"
REPO = "https://github.com/sportstimes/f1"

WANT = re.compile(r"practice|^fp\d$|qualif|sprint|race|^gp$", re.I)
SKIP = re.compile(r"warmup|other", re.I)
LABELS = {"gp": "Race", "fp1": "Practice 1", "fp2": "Practice 2", "fp3": "Practice 3",
          "sprintQualifying": "Sprint Qualifying", "qualifying1": "Qualifying 1",
          "qualifying2": "Qualifying 2", "FinalPractice": "Final Practice"}
MOTOGP_LABELS = {"fp1": "Free Practice 1", "fp2": "Free Practice 2"}


def classify(label):
    """Session name -> (kind, class). Practice is a BLOCK so it never marks you busy;
    qualifying and anything race-shaped is an ANCHOR and carries an alarm."""
    if re.search(r"practice|^fp\d$", label, re.I):
        return "practice", BLOCK
    if re.search(r"qualif", label, re.I):
        return "qualifying", ANCHOR
    return "race", ANCHOR


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def label_for(site, key):
    if site == "motogp" and key in MOTOGP_LABELS:
        return MOTOGP_LABELS[key]
    return LABELS.get(key) or re.sub(r"(?<=[a-z])(?=[A-Z0-9])", " ", key).title()


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "race-calendars-build"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def upstream(key, prefix, site, suffix, this_year):
    """Wanted sessions for the current and future seasons. Returns (events, seasons_available)."""
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
                name = label_for(site, skey)
                kind, cls = classify(skey if re.match(r"^(fp\d|gp)$", skey, re.I) else name)
                # Upstream slugs are not always token-safe: MotoGP's round 3 slug is
                # "United States", and a space inside a UID that ends in "@race-calendars"
                # makes it malformed for any client that reads it as an address. Collapse
                # whitespace only - lowercasing here would change 154 already-published
                # MotoGP UIDs and make every subscriber re-add those events.
                rid = re.sub(r"\s+", "-", race.get("slug") or slug(race["name"]))
                # round in the UID: double-headers repeat a race name within one season
                out.append(event(
                    f"{key}-{year}-r{race.get('round', 0)}-{rid}-{slug(skey)}",
                    f"{prefix}: {title} - {name}", start,
                    start + dt.timedelta(minutes=lengths.get(skey, 60)), race.get("location"),
                    f"Source: sportstimes/f1 (MIT), {REPO} . End time is the typical session length.",
                    REPO, kind=kind, cls=cls))
    return out, have


def hand(key, prefix, skip_seasons):
    """Events from data/<key>.toml. A timed session needs an explicit UTC offset; an event with
    no sessions becomes an all-day anchor. Asserts the file's own hand-counted checksum."""
    path = ROOT / "data" / f"{key}.toml"
    if not path.exists():
        return []
    doc = tomllib.loads(path.read_text(encoding="utf-8"))
    default_min = doc.get("default_minutes", {})
    out, emitted_all = [], 0
    for e in doc.get("event", []):
        url = e.get("source", doc.get("source"))
        checked = e.get("checked", doc.get("checked"))
        src = f"Source: {url} (checked {checked})."
        sessions = e.get("session", [])
        emitted_all += len(sessions) or 1
        if e["season"] in skip_seasons:  # sportstimes publishes this season now: its data wins
            continue
        base = f"{key}-{e['season']}-{slug(e['name'])}"
        for s in sessions:
            start = s["start"]
            if not isinstance(start, dt.datetime) or start.tzinfo is None:
                raise ValueError(f"{path.name}: '{e['name']} / {s['name']}' needs a start with a UTC offset")
            start = start.astimezone(dt.timezone.utc)
            kind, cls = classify(s["name"])
            racey = re.search(r"race|hours|km|500|400|300", s["name"], re.I)
            minutes = s.get("minutes") or default_min.get("race" if racey else "session", 60)
            note = "" if "minutes" in s else " End time is an estimate."
            out.append(event(f"{base}-{slug(s['name'])}", f"{prefix}: {e['name']} - {s['name']}",
                             start, start + dt.timedelta(minutes=minutes), e.get("location"),
                             src + note, url, kind=kind, cls=cls))
        if not sessions:
            first = e.get("start_date", e.get("date"))
            last = e.get("end_date", e.get("date"))
            out.append(event(base, f"{prefix}: {e['name']} (times TBA)", first,
                             last + dt.timedelta(days=1), e.get("location"),
                             src + " Session times not published yet.", url,
                             kind="race", cls=ANCHOR, allday=True))
    # Frozen-data checksum: counts every event in the file, including seasons suppressed this
    # run, so the number does not move when upstream catches up.
    want = doc.get("expected_events")
    if want is not None and want != emitted_all:
        raise AssertionError(f"{path.name}: hand-transcribed data has {emitted_all} events, "
                             f"expected_events says {want} - a transcription slip, or the "
                             f"checksum was not updated with the data")
    return out
