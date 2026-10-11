# Bus RADS

**Routes And Depot Service zones.** An interactive map of Brisbane City Council bus routes, grouped by route-number prefix (38x, 43x, 44x and so on) and showing each group's service zone, with a selector for individual depots or all of them.

This is an unofficial tool, not affiliated with Brisbane City Council or Translink. It is built from Translink's open GTFS feed.

## Status

This is a handoff from a prototype. `CLAUDE.md` has the full context, decisions and next steps.

- `depots/`: route lists for each depot (Toowong, Carina)
- `prototype/scripts/`: the working prototype pipeline (Python) and page template (Leaflet)
- `prototype/reference/route-territories.html`: the built Toowong prototype, self-contained, so open it in a browser

## Building the data

Needs Python 3.11+. Unzip `SEQ_GTFS.zip` into `gtfs/` (either directly or as `gtfs/SEQ_GTFS/`), then:

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m busrads build                  # every depot in depots/
.venv\Scripts\python -m busrads build --depot toowong  # just one
.venv\Scripts\python -m pytest tests
```

Output goes to `site/data/<depot>/` (gitignored), plus a shared `site/data/base.json` for the drawn basemap.

To view the site locally, serve `site/` and open http://127.0.0.1:8765/ (opening `index.html` as a file won't work, as the page fetches its data):

```
.venv\Scripts\python -m http.server 8765 --directory site
``` The build picks the service day itself (the busiest Tue–Thu early in the feed, preferring Wednesday); `--day YYYY-MM-DD` overrides it.

## Data

Contains Translink SEQ GTFS data, licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Feed: https://gtfsrt.api.translink.com.au/GTFS/SEQ_GTFS.zip
