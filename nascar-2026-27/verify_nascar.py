"""Verify the built Formula 1 calendar. Exit 0 means safe to publish.

Imports build_nascar as a module and re-derives the expected event count from the SAME plan()
the build used - never from a hardcoded number, and never by re-parsing its own output blind.
A schema change therefore cannot leave this check measuring something that no longer exists.
"""
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build_nascar as B
from racecal import ics, tz

fails = []


def check(ok, msg):
    if not ok:
        fails.append(msg)


def unfold(raw):
    return raw.replace(b"\r\n ", b"").decode("utf-8").replace("\r\n", "\n")


def fields(block):
    """Parse a VEVENT into name -> value. Parsing, not substring matching: `"HW 9" in text`
    happily matches "HW 99", and the racing equivalent ("Race 1" inside "Race 12") is just as
    wrong."""
    return dict(re.findall(r"^([A-Z-]+)(?:;[^:]*)?:(.*)$", block, re.M))


def when(v):
    return dt.datetime.strptime(v, "%Y%m%d") if len(v) == 8 else dt.datetime.strptime(v, "%Y%m%dT%H%M%SZ")


def main():
    # Shared mechanics prove themselves first; if folding is broken nothing below means anything.
    check(ics.selfcheck() > 0, "ics selfcheck did not run")
    check(tz.selfcheck() > 0, "tz selfcheck did not run")

    events = B.plan()                      # re-derived, not hardcoded
    expected = len(events)
    check(expected > 0, "planner produced no events")

    raw = B.ICS.read_bytes()
    check(raw.startswith(b"BEGIN:VCALENDAR\r\n"), "bad envelope: start")
    check(raw.endswith(b"END:VCALENDAR\r\n"), "bad envelope: end")
    check(raw.count(b"\n") == raw.count(b"\r\n"), "bare LF line endings")
    check(all(len(l) <= 75 for l in raw.split(b"\r\n")), "a line exceeds 75 octets")
    check(b"METHOD:" not in raw, "METHOD present: subscription clients may treat this as an invitation")
    check(b"X-WR-CALNAME:" in raw, "no X-WR-CALNAME: the calendar would show as its filename")

    text = unfold(raw)
    blocks = re.findall(r"BEGIN:VEVENT\n(.*?)END:VEVENT", text, re.S)
    check(len(blocks) == expected, f"{len(blocks)} events in the file, planner says {expected}")

    uids = []
    for b in blocks:
        f = fields(b)
        for need in ("UID", "DTSTAMP", "DTSTART", "DTEND", "SUMMARY"):
            check(need in f, f"event missing {need}: {b[:70]!r}")
        if "DTSTART" in f and "DTEND" in f:
            check(when(f["DTEND"]) > when(f["DTSTART"]), f"end not after start in {f.get('UID')}")
            check(when(f["DTSTART"]).year >= 2025, f"event before 2025 in {f.get('UID')}")
        uids.append(f.get("UID"))
    check(len(uids) == len(set(uids)), "duplicate UIDs")

    # Alarms and busy-state, re-derived from the plan rather than counted by eye.
    want_alarms = sum(1 for e in events
                      if e["cls"] == ics.ANCHOR and not e["allday"] and not e["done"]
                      and e["kind"] in ics.ALARM_LEAD)
    check(text.count("BEGIN:VALARM") == want_alarms,
          f"{text.count('BEGIN:VALARM')} alarms, plan wants {want_alarms}")
    want_free = sum(1 for e in events if e["cls"] == ics.BLOCK)
    check(text.count("TRANSP:TRANSPARENT") == want_free,
          f"{text.count('TRANSP:TRANSPARENT')} transparent events, plan wants {want_free}")

    timed = [e["start"] for e in events if not e["allday"]]
    cdt = [d for d in timed if tz.central_offset(d) == tz.CDT]
    cst = [d for d in timed if tz.central_offset(d) == tz.CST]
    # tz.selfcheck() above already proves the rule on both sides and at both exact boundary
    # instants, every run. This round-trips whatever this calendar actually contains; a feed of
    # only all-day events (IMSA, WRC) legitimately exercises neither side.
    for sample in ([cdt[0]] if cdt else []) + ([cst[0]] if cst else []):
        wall, _ = tz.to_central(sample)
        check(tz.from_central(wall) == sample, f"DST round trip failed for {sample.isoformat()}")
    coverage = f"{len(cdt)} CDT / {len(cst)} CST" if timed else "no timed events"

    # Hygiene as an ALLOWLIST built from the data model, not a denylist of words someone
    # thought to ban. Every word that may appear in a SUMMARY is derived from the events the
    # planner produced; anything else is a string that entered the pipeline from somewhere
    # it should not have.
    allowed = set()
    for e in events:
        allowed |= set(re.findall(r"[A-Za-z0-9']+", e["summary"]))
    for b in blocks:
        for word in re.findall(r"[A-Za-z0-9']+", fields(b).get("SUMMARY", "")):
            check(word in allowed, f"SUMMARY contains {word!r}, which no planned event produced")

    if fails:
        print(f"VERIFY FAIL {KEYLABEL} {len(fails)}")
        print("\n".join(f"  - {m}" for m in fails))
        return 1
    print(f"VERIFY PASS {KEYLABEL} {expected} events, {want_alarms} alarms, {want_free} free, "
          f"DST {coverage}")
    return 0


KEYLABEL = B.KEY
if __name__ == "__main__":
    sys.exit(main())
