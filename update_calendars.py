"""Build, verify and publish every series. THE only command meant to be run by hand.

Order matters and is the whole point: every series is built and verified BEFORE any of them
is published, so a failure in the last series cannot leave the first four published and the
rest stale. The chain aborts on the first failure.

  python update_calendars.py --dry-run   show what would change, write nothing
  python update_calendars.py --yes       no prompts (the GitHub Action runs this)
  python update_calendars.py             prompts per series before writing into docs/

Uploading docs/ to GitHub remains a separate, human step.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from racecal import DTSTAMP, SERIES, TERM
from racecal import ics

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
PAGES = "evan-daruwalla.github.io/race-calendars"


def run(key, script, *args):
    folder = ROOT / f"{key}-{TERM}"
    r = subprocess.run([sys.executable, str(folder / script), *args], cwd=folder)
    return r.returncode


def stage(label, keys, script, args=()):
    print(f"\n=== {label} ===", flush=True)
    for key in keys:
        if run(key, script.format(key=key), *args):
            print(f"\nABORTED at {key}: {script.format(key=key)} failed. Nothing further runs.", flush=True)
            return False
    return True


def combined(keys):
    """One feed carrying every series. Each series' events are re-read from the file that was
    just published, so this can never disagree with what subscribers get."""
    lines, counts, n = [], {}, 0
    for key in keys:
        raw = (DOCS / f"{key}.ics").read_bytes()
        # Unfold to logical lines, then RE-FOLD on the way out. Copying folded continuation
        # lines through unchanged would produce a file whose lines are the sum of two folds;
        # copying them unfolded leaves lines over the 75-octet limit.
        text = raw.replace(b"\r\n ", b"").decode("utf-8").replace("\r\n", "\n")
        blocks = re.findall(r"BEGIN:VEVENT\n(.*?)END:VEVENT", text, re.S)
        counts[key] = len(blocks)
        n += len(blocks)
        for b in blocks:
            lines += ["BEGIN:VEVENT"] + b.strip("\n").split("\n") + ["END:VEVENT"]
    head = ics.calendar("All Racing (race-calendars)", [], DTSTAMP).decode("utf-8")
    head = head.replace("END:VCALENDAR\r\n", "").rstrip("\r\n").split("\r\n")
    out = b"\r\n".join(ics.fold(l) for l in head + lines + ["END:VCALENDAR"]) + b"\r\n"
    ics.write_atomic(DOCS / "all.ics", out)
    return counts, n


def verify_combined(counts, total):
    """The combined feed is assembled here rather than by a series build, so no verify_<key>.py
    covers it. Without this it is the one published file nothing checks - and the first version
    of combined() shipped 624 over-long lines precisely because nothing looked."""
    raw = (DOCS / "all.ics").read_bytes()
    bad = []
    if raw.count(b"\n") != raw.count(b"\r\n"):
        bad.append("bare LF line endings")
    over = [l for l in raw.split(b"\r\n") if len(l) > 75]
    if over:
        bad.append(f"{len(over)} line(s) over 75 octets, first: {over[0][:60]!r}")
    if b"METHOD:" in raw:
        bad.append("METHOD present")
    text = raw.replace(b"\r\n ", b"").decode("utf-8").replace("\r\n", "\n")
    n = len(re.findall(r"BEGIN:VEVENT\n.*?END:VEVENT", text, re.S))
    if n != total:
        bad.append(f"{n} events, the 8 series sum to {total}")
    uids = re.findall(r"^UID:(.*)$", text, re.M)
    if len(uids) != len(set(uids)):
        bad.append(f"{len(uids) - len(set(uids))} duplicate UIDs")
    if bad:
        print("COMBINED FAIL:\n" + "\n".join(f"  - {m}" for m in bad), flush=True)
        return False
    return True


def index(counts, total):
    rows = "\n".join(
        f'<li><b>{SERIES[k][0]}</b>: <a href="webcal://{PAGES}/{k}.ics">subscribe</a> '
        f'&middot; <a href="https://{PAGES}/{k}.ics">https link</a> ({counts[k]} events)</li>'
        for k in counts)
    all_row = (f'<li><b>All series combined</b>: <a href="webcal://{PAGES}/all.ics">subscribe</a> '
               f'&middot; <a href="https://{PAGES}/all.ics">https link</a> ({total} events)</li>')
    ics.write_atomic(DOCS / "index.html", (
        "<!doctype html><meta charset=utf-8><title>race-calendars</title>"
        "<h1>Race calendars</h1><p>One subscribable calendar per series, or all of them combined: "
        "practice, qualifying and races. Times are UTC in the files; calendar apps show them in "
        "your own time zone.</p>"
        "<p>Paste an https link into your calendar app's <b>subscribe by URL</b> option. Use these "
        "addresses directly rather than a shortened link: a redirect adds a hop that some calendar "
        "clients refuse to follow when they subscribe.</p>"
        f"<ul>\n{all_row}\n</ul><hr><ul>\n{rows}\n</ul><p>Source and details: "
        '<a href="https://github.com/Evan-Daruwalla/race-calendars">github.com/Evan-Daruwalla/race-calendars</a></p>\n'
    ).encode("utf-8"))
    ics.write_atomic(DOCS / "manifest.json",
                     (json.dumps({**{k: {"name": SERIES[k][0], "events": v} for k, v in counts.items()},
                                  "all": {"name": "All Racing (race-calendars)", "events": total}},
                                 indent=2) + "\n").encode("utf-8"))
    ics.write_atomic(DOCS / ".nojekyll", b"")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()
    keys = list(SERIES)

    if not stage("BUILD", keys, "build_{key}.py"):
        return 1
    if not stage("VERIFY", keys, "verify_{key}.py"):
        return 1

    pub = (["--dry-run"] if args.dry_run else []) + (["--yes"] if args.yes else [])
    if not stage("PUBLISH", keys, "publish_{key}.py", pub):
        return 1

    if args.dry_run:
        print("\n--dry-run: combined feed and index not regenerated")
        return 0
    counts, total = combined(keys)
    if not verify_combined(counts, total):
        return 1
    index(counts, total)
    print(f"\n=== COMBINED ===\n  all.ics {total} events from {len(counts)} series: "
          + ", ".join(f"{k} {v}" for k, v in counts.items()))
    print("\nDone. docs/ is ready; uploading it to GitHub is a separate, human step.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
