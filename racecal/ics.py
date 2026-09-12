"""RFC 5545 emission: folding, escaping, the two event classes, and an atomic write.

Two event classes, per the architecture:
  ANCHOR  - a real deadline you care about (race, sprint, qualifying). Opaque, carries a
            VALARM. An all-day "times TBA" entry is an anchor with no alarm, because an
            alarm on an all-day event fires at midnight and is pure noise.
  BLOCK   - a session you may want to see but must not be marked busy for (practice).
            TRANSP:TRANSPARENT, no alarm.
"""
import datetime as dt
import os
import tempfile

ANCHOR, BLOCK = "anchor", "block"
ALARM_LEAD = {"race": dt.timedelta(hours=1), "qualifying": dt.timedelta(minutes=30)}


def esc(s):
    """Escape the four characters RFC 5545 reserves inside a text value."""
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):
    """Lines of at most 75 OCTETS; continuation lines start with one space, and that space
    counts toward the 75. Never splits a UTF-8 character."""
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


def event(uid, summary, start, end, location, description, url, kind="race",
          cls=ANCHOR, allday=False, done=False):
    """One calendar event. `kind` drives the alarm lead; `cls` drives busy/free and alarms."""
    return {"uid": uid, "summary": summary, "start": start, "end": end,
            "location": location or "", "description": description, "url": url,
            "kind": kind, "cls": cls, "allday": allday, "done": done}


def _vevent(e, dtstamp):
    d = ";VALUE=DATE" if e["allday"] else ""
    # A finished session keeps its anchor - it is the historical record of when the race was -
    # but loses the alarm and gains a tick, so a glance separates run from upcoming.
    summary = ("\u2713 " + e["summary"]) if e["done"] else e["summary"]
    lines = ["BEGIN:VEVENT", f"UID:{e['uid']}@race-calendars", f"DTSTAMP:{dtstamp}",
             f"DTSTART{d}:{stamp(e['start'], e['allday'])}",
             f"DTEND{d}:{stamp(e['end'], e['allday'])}",
             f"SUMMARY:{esc(summary)}", f"LOCATION:{esc(e['location'])}",
             f"DESCRIPTION:{esc(e['description'])}", f"URL:{e['url']}"]
    if e["cls"] == BLOCK:
        lines.append("TRANSP:TRANSPARENT")
    lead = ALARM_LEAD.get(e["kind"])
    if e["cls"] == ANCHOR and not e["allday"] and not e["done"] and lead:
        mins = int(lead.total_seconds() // 60)
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY",
                  f"TRIGGER:-PT{mins}M", f"DESCRIPTION:{esc(summary)}", "END:VALARM"]
    lines.append("END:VEVENT")
    return lines


def calendar(name, events, dtstamp, desc=None):
    """Full VCALENDAR as bytes. No METHOD property: METHOD makes the file an iTIP message,
    and subscription clients are entitled to treat it as an invitation rather than a feed."""
    desc = desc or f"{name} - practice, qualifying and races. Times in UTC; your calendar app shows them in your time zone."
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//race-calendars//EN",
             "CALSCALE:GREGORIAN", f"X-WR-CALNAME:{esc(name)}", f"X-WR-CALDESC:{esc(desc)}",
             "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
    for e in sorted(events, key=lambda e: (str(e["start"]), e["uid"])):
        lines += _vevent(e, dtstamp)
    lines.append("END:VCALENDAR")
    return b"\r\n".join(fold(l) for l in lines) + b"\r\n"


def write_atomic(path, data):
    """Render-then-replace. `open(path,'w')` truncates immediately, so a bug mid-render would
    already have destroyed the last good file; the caller hands us finished bytes and we swap
    them in with an atomic rename."""
    path = str(path)
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)  # atomic on POSIX and on Windows
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def selfcheck():
    """Assertions only; no I/O. Raises on any failure."""
    n = 0
    # Folding: every physical line within 75 octets, and unfolding restores the original.
    sample = "SUMMARY:" + "S\u00e3o Paulo \u00b7 Aut\u00f3dromo Jos\u00e9 Carlos Pace \u2013 " * 6
    folded = fold(sample)
    assert all(len(p) <= 75 for p in folded.split(b"\r\n")), "fold: a line exceeds 75 octets"
    assert folded.replace(b"\r\n ", b"").decode("utf-8") == sample, "fold: unfold lost bytes"
    n += 2
    # The 75 is octets, not characters: a line of 40 three-byte characters must fold.
    wide = "X:" + "\u4e2d" * 40
    assert len(fold(wide).split(b"\r\n")) > 1, "fold: counted characters, not octets"
    n += 1
    # Escaping, all four reserved characters at once.
    assert esc("a,b;c\\d\ne") == "a\\,b\\;c\\\\d\\ne"
    n += 1
    start = dt.datetime(2026, 9, 13, 19, 0, tzinfo=dt.timezone.utc)
    end = start + dt.timedelta(hours=3)
    mk = lambda **kw: event("u", "Race", start, end, "Loc", "d", "http://x", **kw)
    # An anchor race alarms an hour out; a practice block never alarms and is transparent.
    body = b"\r\n".join(fold(l) for l in _vevent(mk(kind="race", cls=ANCHOR), "20260910T000000Z"))
    assert b"TRIGGER:-PT60M" in body and b"TRANSP" not in body
    blk = b"\r\n".join(fold(l) for l in _vevent(mk(kind="practice", cls=BLOCK), "20260910T000000Z"))
    assert b"TRANSP:TRANSPARENT" in blk and b"VALARM" not in blk
    n += 2
    # A finished anchor keeps the event, drops the alarm, gains the tick.
    fin = b"\r\n".join(fold(l) for l in _vevent(mk(kind="race", cls=ANCHOR, done=True), "20260910T000000Z"))
    assert b"VALARM" not in fin and "\u2713".encode("utf-8") in fin
    n += 1
    # All-day anchors never alarm (a midnight alarm is noise).
    ad = mk(kind="race", cls=ANCHOR, allday=True)
    ad["start"], ad["end"] = dt.date(2027, 2, 13), dt.date(2027, 2, 14)
    assert b"VALARM" not in b"\r\n".join(fold(l) for l in _vevent(ad, "20260910T000000Z"))
    n += 1
    # The envelope carries no METHOD, and CRLF-terminates.
    cal = calendar("T", [mk()], "20260910T000000Z")
    assert cal.startswith(b"BEGIN:VCALENDAR\r\n") and cal.endswith(b"END:VCALENDAR\r\n")
    assert b"METHOD:" not in cal, "METHOD makes this an iTIP message, not a feed"
    assert cal.count(b"\n") == cal.count(b"\r\n"), "bare LF in output"
    n += 3
    return n


if __name__ == "__main__":
    print(f"ics selfcheck OK, {selfcheck()} assertions")
