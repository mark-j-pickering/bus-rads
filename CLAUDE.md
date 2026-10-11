# Bus RADS

**Bus RADS** stands for **R**outes **A**nd **D**epot **S**ervice zones. Use "Bus RADS" as the site title and header, with the subtitle "Brisbane bus routes and depot service zones". The repo and site slug is `bus-rads`. Keep "BCC" and "Translink" out of the name so it reads as an unofficial drivers' tool; they can appear in the subtitle or footer.

The UI says **service zones** rather than "territories" (only the prototype's file names still say "territories").

An interactive map showing how Brisbane City Council bus route numbers divide the city into areas. Routes are grouped by their first two digits (38x = The Gap, 43x = Kenmore South, 44x = Moggill and so on). The map shows each group's service zone, the routes themselves, their stops, and hubs such as UQ.

The prototype was built in a Claude chat session as a single self-contained HTML artifact. This repo moves it to GitHub with a normally hosted site.

- **Live site:** https://mark-j-pickering.github.io/bus-rads/ (public repo, GitHub Pages deployed by Actions)

- **Owner:** Mark (maintainer). His main stack is .NET 8 / WinForms. This project is Python for the data build and plain JS with Leaflet for the site.
- **Live prototype (Toowong only):** https://claude.ai/artifact/5V2HtJj3XMahimLLvPqcDK
- **Reference copy:** `prototype/reference/route-territories.html`. Open it locally. All data is inlined.

## Goals for this repo

1. **Repo and hosting.** Publish to GitHub Pages as a normal static site: one `index.html` plus JSON or GeoJSON data files, not one 3 MB inlined page.
2. **Real basemap.** The artifact sandbox blocked map tiles, so the prototype draws roads, rail and river from GTFS shape geometry (`base.json`). Replace this with an OSM-based tile provider such as OpenFreeMap or CARTO. Avoid tile.openstreetmap.org, whose usage policy rules out heavy use.
3. **Depot selector.** Offer Toowong, Carina and "All". More depots can be added later by dropping a route list in `depots/`.
4. **Automatic refresh.** A scheduled GitHub Action should download the GTFS feed, rebuild the data and redeploy. The current feed runs 10 Oct to 9 Dec 2026.

Mark decided: **don't worry about shared routes.** Some routes are worked by more than one depot (Sherwood runs some of Toowong's). A route simply belongs to every depot list it appears in, and "All" shows it once.

## Progress

Working through the goals one step at a time, Toowong end-to-end first:

1. Done: Python build (`busrads/`, `python -m busrads build`) replacing `prototype/scripts/build.py`. Output matches the prototype for Toowong.
2. Done: static site (`site/`) for Toowong, still on the drawn basemap (`base.json`, built by `busrads/basemap.py`) by Mark's choice.
3. Done: `.github/workflows/deploy.yml` deploys to Pages on every push to `main` or by hand. Builds only the depots in its `DEPOTS` env var (currently `toowong carina`).
   - Since then: legend families and hub sections are collapsible (hubs start collapsed), hovering a header previews it on the map, hub spokes are off by default, and collapsing a family clears a focus or pin inside it.
4. Done: Carina (`depots/carina.json`), viewable at `?depot=carina` until the selector exists. Mark chose two hubs, Woolloongabba station and Carindale Shopping Centre, so the page now handles any number of hubs. One- and two-digit routes (29, 61) are each their own group, named by the number. Carina's area descriptions and suburb label positions are drafts for Mark to check.
5. Next: depot selector and "All", pre-built per selection (see design below).
6. Weekly schedule on the workflow, redeploying only when the feed changed.
7. Docs.

Real tiles (goal 2) are deferred. Findings so far: CARTO raster tiles now need a free API key per site (5M requests/month free for non-commercial use; keys are requested by email at carto.com/basemaps/apikey). OpenFreeMap needs no key and has Positron and Dark styles, but is vector-only, so it needs MapLibre GL plus `@maplibre/maplibre-gl-leaflet`.

## Build notes

- The operator's `route_id` suffix (`-5146` in the current feed) is detected per build as the operator covering most depot route numbers; the build fails if any listed route is missing.
- The service day is the busiest Tue–Thu in the first three weeks of the feed, preferring Wednesday (Wed 14 Oct for the current feed).
- Corridor bands buffer each path and then union, which is ~70x faster than buffering the unioned lines.
- Per-depot config lives in `depots/<id>.json`: `hubs` (name, short name, stop-name regex, optional fixed position), `anchors` (spoke start overrides), `families`, `areas`, `places`. The page reads all of these from `meta.json`.
- Commits use Mark's GitHub noreply address; keep personal details out of the repo.

## Data source

- **GTFS static feed (SEQ):** https://gtfsrt.api.translink.com.au/GTFS/SEQ_GTFS.zip (about 35 MB, licensed CC BY 4.0). The map must credit "Translink SEQ GTFS".
- **School services** are in a separate pilot feed: https://gtfsrt.api.translink.com.au/gtfs/SEQ_SCH_GTFS.zip. Not used yet.
- The feed does **not** record which depot operates a trip. Depot membership comes only from `depots/*.txt`.
- The 7xx numbers in the main feed are **Gold Coast** routes. Toowong's school runs (7xx) and specials (9xx) are not in it, which is why the prototype drops any route starting with 7 or 9.
- `route_id` has a feed-version suffix (`380-5146`). The prototype filters on `-5146` to pick the Brisbane routes. **That suffix will change with the next feed.** Filter by agency or route type instead, and make sure Gold Coast duplicates are excluded.

## Depot route lists (`depots/`)

- The format is one route per line after a header line. Suffixes like `445 Ex`, `706 AM` and `783 OAKLEIGH` are allowed, and the parser keeps the leading route number (regex `N?\d+`).
- `toowong.txt` is Mark's list, including school (7xx) and special (9xx) runs that the main feed doesn't have.
- `carina.txt` was transcribed from Carina's route training record. The sheet also listed the **Suncorp Stadium** and **Gabba Stadium** event precincts, which aren't GTFS routes. If wanted, draw them as manual overlays.

## How the prototype pipeline works (`prototype/scripts/`)

The prototype ran as three steps; `busrads/` now replaces all three, but this describes the method it still follows.

1. **`build.py GTFS_DIR OUT_DIR ROUTE_LIST`**
   - Filters routes to the depot list.
   - Picks one representative weekday (hard-coded to Wed 14 Oct 2026; derive this from the feed instead) and finds its active `service_id`s from `calendar` and `calendar_dates`.
   - Gets weekday trips and their stop_times. stop_times.txt is about 200 MB, so read it in chunks.
   - **Shapes:** each shape is counted per route and direction. A shape used by at least 15% of that route's trips is `main`; the rest are variants. Variants appear only when that route is highlighted.
   - **Stop classification:** each stop gets weekday trip counts per prefix group.
     - `hub`: stop name matches UQ. This is hard-coded and needs to become per-depot config.
     - `cbd`: within 1,700 m of Queen St Mall (153.0251, -27.4698).
     - A group name such as `38x`: that group runs 60% or more of the stop's weekday trips.
     - `shared`: no group reaches 60%.
   - **Zones:** Voronoi cells around stops, each clipped to a 400 m circle, then dissolved by class. This produces `zones.geojson` (dissolved) and `cells.geojson` (one cell per stop, carrying its routes and group percentages).
   - **Route and group bands:** 250 m buffers around main paths and around variants, kept separate. This produces `routebuf.geojson` and `groupbuf.geojson`.
   - **Per-stop details:** route trip counts (`rc`, for example `380:31 382:3`) and other routes from any operator stopping there (`other`). This produces `stops.geojson`.
   - **Group and hub summary:** `meta.json`.
   - Metric work is done in GDA2020 / MGA zone 56 (**EPSG:7856**).
2. **`base.py GTFS_DIR OUT_DIR`** builds the drawn basemap from every bus, rail and ferry shape. Drop this once real tiles are in. It also merges the two UQ hub stops.
3. **`assemble.py SCRATCH_DIR`** inlines Leaflet CSS and all data into `page_template.html`. It also works out spoke anchor points per group, placing each at a representative point of the group's largest zone part, with 40x pinned at Toowong.

Dependencies are in `requirements.txt` (pandas, geopandas, shapely, pyproj, numpy). On the client side the page uses Leaflet 1.9.4.

## UI behaviour to keep (all working in the prototype)

- **Layout:** the map sits on the left with a panel on the right. At 760 px or narrower the panel becomes a bottom sheet. Light and dark themes are both supported.
- **Views:** Zones, Routes and Both. Toggles control UQ spokes, shared corridors and suburb labels. Suburb labels are hand-placed in `PLACES`.
- **Legend:** groups are arranged by family (300s north-west, 400s west, inner-city links). Each row shows the group colour, its prefix, an area description (`AREA` map) and its weekday trip total.
  - Clicking a group row focuses it. The map zooms to the group, shades its full corridor with main paths stronger than variants, and dims other groups.
  - Clicking the row again zooms back out to the fit-all view.
- **Route chips** under each group:
  - Hovering previews the route. Clicking pins it and zooms to it.
  - The highlight shows a 250 m band, a solid main path, dashed variants, and **only the stops that route serves**. All other stops are hidden.
  - Unpinning returns to the focused group, or to the fit-all view if no group is focused.
- **Hover labels** use the page's own hit testing rather than Leaflet's canvas hover, which got stuck after redraws.
  - A zone shows its prefix and area.
  - A shared area shows how its trips split, for example "41x 62% · 47x 38%", and its routes.
  - A stop shows its name, a colour tag for each route with that route's weekday trip count, "Serviced N times each weekday by these routes", and other routes stopping there.
  - Stop labels take priority near stops.
- **Stop popups** (on click) contain tappable route tags that pin that route, which is how highlighting works on phones.
- **Fit-all view:** the page opens fitted to the bounds of all zones with 16 px padding, and returns there when selections are cleared. `zoomSnap` is 0.25 and `zoomDelta` is 0.5.
- **UQ hub card:** weekday stop visits per group at Chancellors Place (Toowong: 41x 333, 42x 126, 40x 96, 43x 48). Spokes run from each group's anchor to UQ, with line width scaled to visits.

## Design for the depot selector (agreed, not built)

- **Colour by prefix group, not by depot**, so 41x looks the same in every view.
- **Pre-build each selection.** Which group "owns" a stop depends on which routes are included, so build zones, cells and summaries once per depot and once for "All". Write them to `data/<depot>/`.
- **"All" needs a bigger palette,** possibly 25 or more groups. Give each hundred its own hue family (2xx south and east, 3xx north-west, 4xx west, and so on) with a different shade for each prefix.
- **Hubs per depot,** set in config. "All" shows every depot's hubs. Carina's hubs are not yet known; let the data suggest them by finding stops visited by the most groups.
- `AREA` descriptions and suburb labels should move into per-depot config. Carina's 2xx areas still need writing.

## Findings so far (Toowong)

- 13 groups with 2,329 weekday trips.
- 3xx is the north-west: 34x Stafford, 36x Brookside and Everton Park, 37x Ashgrove and Bardon, 38x The Gap, 39x Mitchelton.
- 4xx is the west: 41x UQ, Taringa and Indooroopilly; 42x Chapel Hill; 43x Kenmore South, Fig Tree Pocket and Brookfield; 44x Moggill; 47x Toowong, Rainworth and Mt Coot-tha.
- Outliers in Toowong's list: 199 (West End to Teneriffe), 309 (RBWH) and 347–349 (Stafford).
- 40x (route 402) shares every stop with 41x and 47x, so its solid zone is a single stop. Its corridor only shows when focused or highlighted. This is expected behaviour.
- Route 380's Payne Rd variant is used by only 2 weekday trips.

## Open items

- Pick a tile provider: CARTO (needs a key) or OpenFreeMap (needs MapLibre GL). See Progress.
- Decide whether to add the school feed as a separate layer.
- Mark to check Carina's draft area descriptions and suburb labels (`depots/carina.json`).
- Optionally draw the event precinct overlays (Suncorp, Gabba).
