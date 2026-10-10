# Bus RADS

**Routes And Depot Service zones.** An interactive map of Brisbane City Council bus routes, grouped by route-number prefix (38x, 43x, 44x and so on) and showing each group's service zone, with a selector for individual depots or all of them.

This is an unofficial tool, not affiliated with Brisbane City Council or Translink. It is built from Translink's open GTFS feed.

## Status

This is a handoff from a prototype. `CLAUDE.md` has the full context, decisions and next steps.

- `depots/`: route lists for each depot (Toowong, Carina)
- `prototype/scripts/`: the working prototype pipeline (Python) and page template (Leaflet)
- `prototype/reference/route-territories.html`: the built Toowong prototype, self-contained, so open it in a browser

## Data

Contains Translink SEQ GTFS data, licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Feed: https://gtfsrt.api.translink.com.au/GTFS/SEQ_GTFS.zip
