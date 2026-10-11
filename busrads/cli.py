"""python -m busrads build [--gtfs DIR] [--out DIR] [--depot ID ...]"""
import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from . import analysis, depots, export
from .feed import BuildError, Feed, pick_service_day, select_routes

ROOT = Path(__file__).resolve().parent.parent


def default_gtfs():
    """gtfs/ holds the unzipped feed, either directly or in gtfs/SEQ_GTFS/."""
    nested = ROOT / "gtfs" / "SEQ_GTFS"
    return nested if (nested / "routes.txt").exists() else ROOT / "gtfs"


def log(msg, t0=[time.perf_counter()]):
    print(f"[{time.perf_counter() - t0[0]:6.1f}s] {msg}", flush=True)


def build(gtfs_dir, out_dir, depots_dir, ids, day=None):
    sel = [depots.load_depot(depots_dir, i) for i in ids]
    log(f"loading feed from {gtfs_dir}")
    feed = Feed(gtfs_dir)
    wanted = sorted({r for d in sel for r in d.feed_routes}, key=depots.route_key)
    routes, op = select_routes(feed.routes, wanted)
    log(f"{len(routes)} routes, operator suffix -{op}")

    if day is None:
        day = pick_service_day(feed.start, feed.calendar, feed.calendar_dates,
                               feed.trips[feed.trips.route_id.isin(set(routes.route_id))])
    day_trips = feed.day_trips(day)
    log(f"service day {day:%a %d %b %Y}: {len(day_trips)} trips across all operators")

    stop_times = feed.stop_times(day_trips.trip_id)
    log(f"{len(stop_times)} stop_times rows")
    shape_ids = day_trips[day_trips.route_id.isin(set(routes.route_id))].shape_id
    shape_points = feed.shapes(shape_ids)
    log(f"{shape_points.shape_id.nunique()} shapes")

    built = []
    for d in sel:
        res = analysis.build_selection(
            feed, d, routes[routes.route_short_name.isin(d.feed_routes)],
            day_trips, stop_times, shape_points)
        dest = Path(out_dir) / d.id
        for key in ("zones", "cells", "routes", "routebuf", "groupbuf", "stops"):
            export.write_geojson(res[key], dest / f"{key}.geojson")
        meta = dict(
            depot=d.id, name=d.name, day=str(day), feed=feed.label,
            feed_start=str(feed.start), feed_end=str(feed.end),
            groups=res["groups"], hubs=res["hubs"],
            families=d.families, areas=d.areas, places=d.places,
            not_in_feed=[x for x in d.routes if not depots.in_main_feed(x)],
        )
        export.write_json(meta, dest / "meta.json")
        log(f"{d.id}: {len(res['groups'])} groups, {res['trips']} trips -> {dest}")
        built.append(dict(id=d.id, name=d.name))

    export.write_json(dict(feed=feed.label, day=str(day), depots=built), Path(out_dir) / "index.json")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="busrads")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build site data from the GTFS feed")
    b.add_argument("--gtfs", type=Path, default=None, help="unzipped GTFS directory (default: gtfs/)")
    b.add_argument("--out", type=Path, default=ROOT / "site" / "data")
    b.add_argument("--depots", type=Path, default=ROOT / "depots")
    b.add_argument("--depot", nargs="*", help="depot ids to build (default: all lists in depots/)")
    b.add_argument("--day", type=dt.date.fromisoformat, help="service day override, YYYY-MM-DD")
    a = ap.parse_args(argv)
    try:
        build(a.gtfs or default_gtfs(), a.out, a.depots, a.depot or depots.depot_ids(a.depots), a.day)
    except BuildError as e:
        print(f"build failed: {e}", file=sys.stderr)
        return 1
    return 0
