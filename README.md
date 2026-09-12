# race-calendars

Subscribable calendars for 8 racing series, with practice, qualifying and races, rebuilt every
day.

| Series | Subscribe (paste into your calendar app) |
|---|---|
| Formula 1 | https://evan-daruwalla.github.io/race-calendars/f1.ics |
| Formula E | https://evan-daruwalla.github.io/race-calendars/formula-e.ics |
| IndyCar | https://evan-daruwalla.github.io/race-calendars/indycar.ics |
| MotoGP | https://evan-daruwalla.github.io/race-calendars/motogp.ics |
| NASCAR Cup Series | https://evan-daruwalla.github.io/race-calendars/nascar.ics |
| FIA WEC | https://evan-daruwalla.github.io/race-calendars/wec.ics |
| IMSA WeatherTech | https://evan-daruwalla.github.io/race-calendars/imsa.ics |
| FIA WRC | https://evan-daruwalla.github.io/race-calendars/wrc.ics |

Add one with your calendar app's "subscribe by URL" or "from URL" option. Don't download
the file: a subscription keeps updating, a downloaded copy doesn't.

## Where the dates come from

- **F1, Formula E, IndyCar, MotoGP:** every session from
  [sportstimes/f1](https://github.com/sportstimes/f1) (MIT), the project behind f1calendar.com.
- **NASCAR, WEC, IMSA, WRC, plus announced seasons sportstimes hasn't added yet:** entered by hand
  from each series' official website into `data/*.toml`. Every event links to the page it came
  from.
- **Events with no published times** show as all-day events marked "(times TBA)". When
  sportstimes adds a season, its timed data replaces the hand-entered dates for that season.

## Good to know

- **Times are stored in UTC.** Your calendar app shows them in your own time zone.
- **End times** use typical session lengths. Where a length was estimated, the event says so.
- **Updates:** the build runs daily at 11:17 UTC. Calendar apps poll on their own schedule, so a
  change can take up to about a day to show up (Google Calendar is the slow one).
- **Not affiliated with or endorsed by** any series, sanctioning body or rights holder. Series
  names are used only to say what each calendar covers.

## License

Code: MIT ([LICENSE](LICENSE)). The sportstimes data is MIT too; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
