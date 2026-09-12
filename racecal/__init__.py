"""Shared mechanics for the per-series calendar projects.

The architecture keeps one folder per series with its own build/verify/publish scripts. The
RFC 5545 machinery lives here instead of being copied into each of them: eight copies of the
line-folding code would be eight copies of every folding bug, and the folding rule is not a
per-series fact. What IS per-series - the data, the identity, the integrity checks - stays in
that series' own build script, which remains its only source of truth.
"""

# Fixed, so unchanged data rebuilds byte-identical. publish compares old against new bytes and
# skips the upload when nothing moved; a live timestamp would make every build look changed.
DTSTAMP = "20260910T000000Z"

SERIES = {
    #  key            name                                             prefix      sportstimes  suffix
    "f1":        ("Formula 1",                                        "F1",       "f1",        " Grand Prix"),
    "formula-e": ("Formula E",                                        "FE",       "fe",        ""),
    "indycar":   ("IndyCar Series",                                   "IndyCar",  "indycar",   ""),
    "motogp":    ("MotoGP",                                           "MotoGP",   "motogp",    " Grand Prix"),
    "nascar":    ("NASCAR Cup Series",                                "NASCAR",   None,        ""),
    "wec":       ("FIA World Endurance Championship",                 "WEC",      None,        ""),
    "imsa":      ("IMSA WeatherTech SportsCar Championship",          "IMSA",     None,        ""),
    "wrc":       ("FIA World Rally Championship",                     "WRC",      None,        ""),
}

TERM = "2026-27"
