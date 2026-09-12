"""Self-check for the generated calendars. Exits 1 on any failure.

Checks every docs/<series>.ics against RFC 5545 basics (CRLF, 75-octet lines, required fields,
unique UIDs, end after start) and against docs/manifest.json (event counts), plus a folding
round-trip on a long multi-byte line.
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

from build import SERIES, fold

OUT = Path(__file__).resolve().parent / "docs"
fails = []


def check(ok, msg):
    if not ok:
        fails.append(msg)


# Folding round-trip: long line with multi-byte characters survives fold + unfold unchanged.
sample = "SUMMARY:" + "São Paulo · Autódromo José Carlos Pace – " * 6
folded = fold(sample)
check(all(len(p) <= 75 for p in folded.split(b"\r\n")), "fold: a line is over 75 octets")
check(folded.replace(b"\r\n ", b"").decode("utf-8") == sample, "fold: unfold does not restore the original")


def when(v):
    return dt.datetime.strptime(v, "%Y%m%d") if len(v) == 8 else dt.datetime.strptime(v, "%Y%m%dT%H%M%SZ")


manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
for key in list(SERIES) + ["all"]:
    raw = (OUT / f"{key}.ics").read_bytes()
    check(raw.startswith(b"BEGIN:VCALENDAR\r\n") and raw.endswith(b"END:VCALENDAR\r\n"), f"{key}: bad envelope")
    check(raw.count(b"\n") == raw.count(b"\r\n"), f"{key}: bare LF line endings")
    check(all(len(l) <= 75 for l in raw.split(b"\r\n")), f"{key}: a line is over 75 octets")
    text = raw.replace(b"\r\n ", b"").decode("utf-8").replace("\r\n", "\n")  # unfold, then plain \n for the field regex
    blocks = re.findall(r"BEGIN:VEVENT\n(.*?)END:VEVENT", text, re.S)
    check(len(blocks) == manifest[key]["events"], f"{key}: {len(blocks)} events, manifest says {manifest[key]['events']}")
    check(len(blocks) > 0, f"{key}: no events at all")
    uids = []
    for b in blocks:
        f = dict(re.findall(r"^([A-Z-]+)(?:;[^:]*)?:(.*)$", b, re.M))
        for need in ("UID", "DTSTAMP", "DTSTART", "DTEND", "SUMMARY"):
            check(need in f, f"{key}: event missing {need}: {b[:80]!r}")
        if "DTSTART" in f and "DTEND" in f:
            check(when(f["DTEND"]) > when(f["DTSTART"]), f"{key}: end not after start in {f.get('UID')}")
            # 2025 floor, not 2026: Formula E seasons start the December before their end year
            check(when(f["DTSTART"]).year >= 2025, f"{key}: event before 2025 in {f.get('UID')}")
        uids.append(f.get("UID"))
    check(len(uids) == len(set(uids)), f"{key}: duplicate UIDs")

# the combined feed must hold every series event: without this, a whole series can vanish from
# all.ics and still pass, because all.ics and its manifest entry come from the same build run
check(manifest["all"]["events"] == sum(manifest[k]["events"] for k in SERIES),
      f"all: {manifest['all']['events']} events, the 8 series sum to {sum(manifest[k]['events'] for k in SERIES)}")

if fails:
    print("CHECK FAIL", len(fails))
    print("\n".join(fails))
    sys.exit(1)
print(f"CHECK PASS {len(SERIES)} calendars plus 1 combined feed, {manifest['all']['events']} events")
