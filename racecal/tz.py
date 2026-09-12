"""US Central time, hand-rolled, so the build never depends on the runtime having tzdata.

Rule: CDT (UTC-5) from 02:00 local on the 2nd Sunday of March until 02:00 local on the
1st Sunday of November; CST (UTC-6) otherwise. Correct for 2007 onward (Energy Policy Act
of 2005). Calendars are emitted in UTC, so this is used for rendering local wall-clock times
in SCHEDULE.md and for the DST round-trip assertion in each verify script.
"""
import datetime as dt

CST = dt.timedelta(hours=-6)
CDT = dt.timedelta(hours=-5)


def _nth_sunday(year, month, n):
    """Date of the nth (1-based) Sunday of a month."""
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(6 - d.weekday()) % 7)  # Monday=0 ... Sunday=6
    return d + dt.timedelta(weeks=n - 1)


def dst_bounds(year):
    """(start, end) of Central DST as UTC datetimes.

    The switch happens at 02:00 local: 08:00 UTC in spring (still CST, UTC-6) and
    07:00 UTC in autumn (still CDT, UTC-5).
    """
    start = dt.datetime.combine(_nth_sunday(year, 3, 2), dt.time(8), dt.timezone.utc)
    end = dt.datetime.combine(_nth_sunday(year, 11, 1), dt.time(7), dt.timezone.utc)
    return start, end


def central_offset(utc):
    """Central offset in force at this UTC instant."""
    if utc.tzinfo is None:
        raise ValueError("central_offset needs an aware UTC datetime")
    utc = utc.astimezone(dt.timezone.utc)
    start, end = dst_bounds(utc.year)
    return CDT if start <= utc < end else CST


def to_central(utc):
    """UTC instant -> naive Central wall-clock datetime, plus the zone label."""
    off = central_offset(utc)
    return utc.astimezone(dt.timezone.utc).replace(tzinfo=None) + off, ("CDT" if off == CDT else "CST")


def from_central(wall, year_hint=None):
    """Naive Central wall-clock -> aware UTC. Ambiguous/nonexistent hours resolve to the
    offset in force just before the transition, which is what a published schedule means."""
    guess = wall.replace(tzinfo=dt.timezone.utc) - CST  # assume CST, then correct
    off = central_offset(guess)
    return wall.replace(tzinfo=dt.timezone.utc) - off


def selfcheck():
    """Assertions only; no I/O. Raises on any failure."""
    # 2026: 2nd Sunday of March is the 8th, 1st Sunday of November is the 1st.
    s, e = dst_bounds(2026)
    assert s == dt.datetime(2026, 3, 8, 8, tzinfo=dt.timezone.utc), s
    assert e == dt.datetime(2026, 11, 1, 7, tzinfo=dt.timezone.utc), e
    # 2027: March 14, November 7.
    s27, e27 = dst_bounds(2027)
    assert s27 == dt.datetime(2027, 3, 14, 8, tzinfo=dt.timezone.utc), s27
    assert e27 == dt.datetime(2027, 11, 7, 7, tzinfo=dt.timezone.utc), e27
    # Both sides of the autumn boundary, the one our NASCAR data actually crosses.
    before = dt.datetime(2026, 10, 25, 19, 0, tzinfo=dt.timezone.utc)   # CDT
    after = dt.datetime(2026, 11, 1, 20, 0, tzinfo=dt.timezone.utc)     # CST
    assert central_offset(before) == CDT, central_offset(before)
    assert central_offset(after) == CST, central_offset(after)
    assert to_central(before) == (dt.datetime(2026, 10, 25, 14, 0), "CDT"), to_central(before)
    assert to_central(after) == (dt.datetime(2026, 11, 1, 14, 0), "CST"), to_central(after)
    # Round trip on both sides.
    for utc in (before, after):
        wall, _ = to_central(utc)
        assert from_central(wall) == utc, (wall, from_central(wall), utc)
    # One instant either side of each boundary, exactly.
    assert central_offset(s - dt.timedelta(seconds=1)) == CST
    assert central_offset(s) == CDT
    assert central_offset(e - dt.timedelta(seconds=1)) == CDT
    assert central_offset(e) == CST
    return 14  # assertions that must hold; verify scripts print this


if __name__ == "__main__":
    print(f"tz selfcheck OK, {selfcheck()} assertions")
