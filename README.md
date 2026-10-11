# Bus RADS

**Routes And Depot Service zones.** An interactive map of Brisbane City Council bus routes, grouped by route-number prefix (38x, 43x, 44x and so on) and showing each group's service zone.

**Live site:** https://mark-j-pickering.github.io/bus-rads/

This is an unofficial tool, not affiliated with Brisbane City Council or Translink. It is built from Translink's open GTFS feed.

## Status

Toowong and Carina depots are live, plus an "All" view of every Brisbane City Council bus route, with a selector between them (link straight to one with `#toowong`, `#carina` or `#all`). A weekly automatic refresh and real map tiles are next. `CLAUDE.md` has the full context, decisions and plan.

- `busrads/`: the Python data build
- `depots/`: route lists (`<depot>.txt`) and display config (`<depot>.json`) for each depot
- `site/`: the static site (`index.html`, `css/`, `js/`); the build writes `site/data/`
- `.github/workflows/deploy.yml`: downloads the feed, builds and deploys to GitHub Pages
- `prototype/`: the original single-page prototype, kept for reference

## Building the data

Needs Python 3.11+. Unzip `SEQ_GTFS.zip` into `gtfs/` (either directly or as `gtfs/SEQ_GTFS/`), then:

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m busrads build                  # every depot in depots/
.venv\Scripts\python -m busrads build --depot toowong  # just one
.venv\Scripts\python -m pytest tests
```

Output goes to `site/data/<depot>/` (gitignored), plus `site/data/all/` (every route the operator runs), a shared `site/data/base.json` for the drawn basemap, and `site/data/index.json` listing what was built. To add a depot, drop `<id>.txt` (route list) and `<id>.json` (display config) into `depots/`. The build picks the service day itself (the busiest Tue–Thu early in the feed, preferring Wednesday); `--day YYYY-MM-DD` overrides it.

## Viewing it locally

Double-click `serve.bat`. It builds the data if there is none yet, serves `site/` and opens http://127.0.0.1:8765/. Opening `index.html` directly as a file won't work, as the page fetches its data.

## Deploying

Every push to `main` runs the workflow, which downloads the latest feed, runs the tests, builds the data and publishes to GitHub Pages. It can also be run by hand from the Actions tab.

## Data

Contains Translink SEQ GTFS data, licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Feed: https://gtfsrt.api.translink.com.au/GTFS/SEQ_GTFS.zip
