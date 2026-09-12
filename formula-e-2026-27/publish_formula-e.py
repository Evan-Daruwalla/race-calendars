"""Publish the Formula 1 calendar into docs/, which GitHub Pages serves to subscribers.

Order is the point: rebuild, verify, and ABORT before touching anything if either fails.
Then compare against what subscribers are actually being served right now, show what would
change at the level of events rather than lines, and ask before landing it.

  --dry-run   show the diff, never write
  --yes       skip the prompt (for the orchestrator and scheduled runs)

Uploading to GitHub stays a human action: this only stages the bytes in docs/.
"""
import argparse
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import importlib

# the module name contains a hyphen, so it cannot be imported with `import ... as`
B = importlib.import_module("build_formula-e")
from racecal import ics

LIVE = f"https://evan-daruwalla.github.io/race-calendars/{B.KEY}.ics"
DEST = Path(__file__).resolve().parent.parent / "docs" / f"{B.KEY}.ics"


def run(script):
    """Run a sibling script with the same interpreter; return its exit code."""
    return subprocess.run([sys.executable, str(Path(__file__).resolve().parent / script)]).returncode


def parse(raw):
    """UID -> (summary, dtstart). Parsed, never substring-matched."""
    text = raw.replace(b"\r\n ", b"").decode("utf-8", "replace").replace("\r\n", "\n")
    out = {}
    for b in re.findall(r"BEGIN:VEVENT\n(.*?)END:VEVENT", text, re.S):
        f = dict(re.findall(r"^([A-Z-]+)(?:;[^:]*)?:(.*)$", b, re.M))
        if "UID" in f:
            out[f["UID"]] = (f.get("SUMMARY", ""), f.get("DTSTART", ""))
    return out


def fetch_published():
    """What subscribers get right now. Falls back to the file in docs/ when offline, and says
    which one it used - a diff against the wrong baseline is worse than no diff."""
    try:
        with urllib.request.urlopen(LIVE, timeout=30) as r:
            return r.read(), f"live feed {LIVE}"
    except (urllib.error.URLError, TimeoutError) as e:
        if DEST.exists():
            return DEST.read_bytes(), f"local docs/{B.KEY}.ics (live fetch failed: {e})"
        return b"", f"nothing published yet (live fetch failed: {e})"


def summarise(old, new):
    o, n = parse(old), parse(new)
    added = [u for u in n if u not in o]
    removed = [u for u in o if u not in n]
    retitled = [u for u in n if u in o and o[u][0] != n[u][0]]
    moved = [u for u in n if u in o and o[u][1] != n[u][1]]
    return o, n, added, removed, retitled, moved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="show the diff and never write")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = ap.parse_args()

    if run(f"build_{B.KEY}.py") or run(f"verify_{B.KEY}.py"):
        print(f"{B.KEY}: build or verify failed, nothing published")
        return 1

    new = B.ICS.read_bytes()
    old, where = fetch_published()
    print(f"{B.KEY}: comparing against {where}")

    if old == new:
        print(f"{B.KEY}: byte-for-byte identical, nothing to publish")
        return 0

    o, n, added, removed, retitled, moved = summarise(old, new)
    print(f"{B.KEY}: {len(o)} published -> {len(n)} built  "
          f"(+{len(added)} added, -{len(removed)} removed, {len(retitled)} retitled, {len(moved)} rescheduled)")
    for label, uids, src in (("added", added, n), ("removed", removed, o),
                             ("retitled", retitled, n), ("rescheduled", moved, n)):
        for u in uids[:15]:
            print(f"    {label:12} {src[u][1]:16} {src[u][0][:70]}")
        if len(uids) > 15:
            print(f"    {label:12} ... and {len(uids) - 15} more")

    if args.dry_run:
        print(f"{B.KEY}: --dry-run, nothing written")
        return 0
    if not args.yes:
        if input(f"publish {B.KEY} to docs/? [y/N] ").strip().lower() != "y":
            print(f"{B.KEY}: declined, nothing written")
            return 0

    ics.write_atomic(DEST, new)
    print(f"{B.KEY}: wrote {DEST}. Uploading to GitHub is a separate, human step.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
