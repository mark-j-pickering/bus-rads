"""Reading the GTFS feed: operator detection, service-day choice, day-filtered tables."""
import datetime as dt
from pathlib import Path

import pandas as pd

BUS = "3"
CHUNK = 2_000_000


class BuildError(Exception):
    pass


def read(gtfs_dir, name, **kw):
    return pd.read_csv(Path(gtfs_dir) / f"{name}.txt", dtype=str, **kw)


def operator_of(route_id):
    """route_id is '<number>-<operator>', e.g. '380-5146'. The suffix separates
    Brisbane's routes from Gold Coast routes with the same number, and changes
    between feeds, so it is detected rather than hard-coded."""
    return route_id.rsplit("-", 1)[-1]


def select_routes(routes, wanted):
    """Pick the bus routes for the wanted route numbers, all from one operator.

    The operator is whichever covers the most wanted numbers. Raises if any
    wanted number isn't run by that operator, so a stale depot list or a feed
    change fails the build instead of silently dropping routes.
    """
    bus = routes[routes.route_type == BUS].copy()
    bus["operator"] = bus.route_id.map(operator_of)
    hits = bus[bus.route_short_name.isin(wanted)]
    if hits.empty:
        raise BuildError("none of the depot routes are in the feed")
    op = hits.groupby("operator").route_short_name.nunique().idxmax()
    sel = hits[hits.operator == op]
    missing = sorted(set(wanted) - set(sel.route_short_name))
    if missing:
        raise BuildError(f"routes not found for operator {op}: {' '.join(missing)}")
    dup = sel[sel.route_short_name.duplicated()].route_short_name.tolist()
    if dup:
        raise BuildError(f"route numbers appear more than once for operator {op}: {' '.join(dup)}")
    return sel.drop(columns="operator"), op


def active_services(calendar, calendar_dates, day):
    ds = day.strftime("%Y%m%d")
    wd = day.strftime("%A").lower()
    c = calendar
    act = set(c[(c[wd] == "1") & (c.start_date <= ds) & (c.end_date >= ds)].service_id)
    cd = calendar_dates[calendar_dates.date == ds]
    act |= set(cd[cd.exception_type == "1"].service_id)
    act -= set(cd[cd.exception_type == "2"].service_id)
    return act


def parse_date(s):
    return dt.datetime.strptime(s, "%Y%m%d").date()


def pick_service_day(feed_start, calendar, calendar_dates, trips, search_days=21):
    """The representative weekday: the Tue-Thu in the first few weeks of the feed
    on which the given trips run most often. Ties go to Wednesday, then the
    earliest date. Mondays and Fridays are skipped as they're likelier to be
    public holidays or have Friday-only extras."""
    best = None
    for i in range(search_days):
        day = feed_start + dt.timedelta(days=i)
        if day.weekday() not in (1, 2, 3):
            continue
        n = int(trips.service_id.isin(active_services(calendar, calendar_dates, day)).sum())
        key = (-n, day.weekday() != 2, day)
        if best is None or key < best[0]:
            best = (key, day, n)
    if best is None or best[2] == 0:
        raise BuildError("no Tue-Thu with service found near the start of the feed")
    return best[1]


class Feed:
    """The parts of the GTFS feed the build needs, loaded once and shared by
    every depot selection."""

    def __init__(self, gtfs_dir):
        self.dir = Path(gtfs_dir)
        if not (self.dir / "routes.txt").exists():
            raise BuildError(f"no GTFS feed in {self.dir}")
        self.routes = read(self.dir, "routes")
        self.stops = read(self.dir, "stops")
        self.stops[["stop_lat", "stop_lon"]] = self.stops[["stop_lat", "stop_lon"]].astype(float)
        self.calendar = read(self.dir, "calendar")
        self.calendar_dates = read(self.dir, "calendar_dates")
        self.trips = read(self.dir, "trips", usecols=["route_id", "service_id", "trip_id", "direction_id", "shape_id"])
        info = read(self.dir, "feed_info").iloc[0]
        self.start = parse_date(info.feed_start_date)
        self.end = parse_date(info.feed_end_date)

    @property
    def label(self):
        f = lambda d: f"{d.day} {d.strftime('%b')}"
        return f"Translink SEQ GTFS, {f(self.start)} – {f(self.end)} {self.end.year}"

    def day_trips(self, day):
        return self.trips[self.trips.service_id.isin(active_services(self.calendar, self.calendar_dates, day))]

    def stop_times(self, trip_ids):
        """trip_id/stop_id rows for the given trips. stop_times.txt is ~200 MB, so it's read in chunks."""
        ids = set(trip_ids)
        parts = [ch[ch.trip_id.isin(ids)] for ch in
                 pd.read_csv(self.dir / "stop_times.txt", dtype=str, usecols=["trip_id", "stop_id"], chunksize=CHUNK)]
        return pd.concat(parts, ignore_index=True)

    def shapes(self, shape_ids):
        ids = set(shape_ids)
        parts = [ch[ch.shape_id.isin(ids)] for ch in
                 pd.read_csv(self.dir / "shapes.txt", dtype={"shape_id": str}, chunksize=CHUNK)]
        return pd.concat(parts, ignore_index=True).sort_values(["shape_id", "shape_pt_sequence"])
