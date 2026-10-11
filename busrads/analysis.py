"""Service-zone analysis for one depot selection.

All metric work is in GDA2020 / MGA zone 56 (EPSG:7856); outputs are WGS84.
"""
import re

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, MultiPoint, Point, box
from shapely.ops import voronoi_diagram

from .depots import group_of, route_key

METRIC = 7856
WGS84 = 4326

MAIN_SHAPE_SHARE = 0.15            # a shape used by >= 15% of a route+direction's trips is a main path
DOMINANT_SHARE = 0.6               # a group owns a stop if it runs >= 60% of the stop's trips
CBD_CENTRE = (153.0251, -27.4698)  # Queen St Mall
CBD_RADIUS_M = 1700
CATCHMENT_M = 400                  # Voronoi cells are clipped to this walk radius
BAND_M = 250                       # route/group corridor half-width
MIN_VARIANT_AREA_M2 = 20000


def rsort(routes):
    return sorted(set(routes), key=route_key)


def build_selection(feed, depot, routes, day_trips, stop_times, shape_points):
    """Every output for one depot selection.

    routes: the depot's rows from routes.txt (one operator). day_trips: all of
    the service day's trips (any operator). stop_times: trip_id/stop_id rows for
    day_trips. shape_points: shapes.txt rows covering at least this depot's shapes.
    """
    r = routes.copy()
    r["group"] = r.route_short_name.map(group_of)
    ta = day_trips.merge(r[["route_id", "route_short_name", "group"]], on="route_id")
    st = stop_times[stop_times.trip_id.isin(set(ta.trip_id))].merge(
        ta[["trip_id", "route_short_name", "group"]], on="trip_id")
    rtrips = ta.groupby("route_short_name").size().to_dict()
    names = dict(zip(r.route_short_name, r.route_long_name))

    rt = route_shapes(ta, shape_points, names, rtrips)
    gp = classify_stops(feed.stops, st, depot.hubs)
    cells, zones = catchments(gp)
    routebuf, groupbuf = corridors(rt)
    stops_out = stop_details(gp, st, stop_times, day_trips, r, feed.routes)
    hubs = hub_summary(gp, depot.hubs)
    groups = group_summary(r, rtrips, gp, zones, hubs)
    add_anchors(groups, zones, depot.anchors)
    rt_out = rt[["route_short_name", "group", "direction_id", "name", "trips", "main", "n", "geometry"]].copy()
    rt_out["geometry"] = rt_out.simplify(6)

    return dict(
        routes=rt_out,
        routebuf=routebuf, groupbuf=groupbuf, zones=zones,
        cells=cells[["cls", "r", "g", "geometry"]],
        stops=stops_out[["stop_name", "cls", "ntrips", "routes", "rc", "other", "geometry"]],
        groups=groups, hubs=hubs, trips=len(ta),
    )


def route_shapes(ta, shape_points, names, rtrips):
    """One row per route+direction+shape, flagged main or variant, in metres."""
    sc = ta.groupby(["route_short_name", "group", "direction_id", "shape_id"]).size().reset_index(name="n")
    tot = sc.groupby(["route_short_name", "direction_id"]).n.transform("sum")
    sc["main"] = sc.n / tot >= MAIN_SHAPE_SHARE
    sh = shape_points[shape_points.shape_id.isin(set(sc.shape_id))]
    geom = {k: LineString(list(zip(v.shape_pt_lon, v.shape_pt_lat))) for k, v in sh.groupby("shape_id")}
    sc["geometry"] = sc.shape_id.map(geom)
    sc["name"] = sc.route_short_name.map(names)
    sc["trips"] = sc.route_short_name.map(rtrips)
    rt = gpd.GeoDataFrame(sc, geometry="geometry", crs=WGS84).to_crs(METRIC)
    return rt


def hub_of(name, hubs):
    n = name.lower()
    for h in hubs:
        if re.search(h["match"], n):
            return h["name"]
    return None


def classify_stops(stops, st, hubs):
    """Each served stop with its per-group weekday trip counts and its class:
    a hub name's class 'hub', 'cbd', a dominant group such as '38x', or 'shared'."""
    sg = st.groupby(["stop_id", "group"]).size().unstack(fill_value=0)
    srt = st.groupby("stop_id").route_short_name.agg(rsort)
    s = stops.set_index("stop_id").loc[sg.index]
    gp = gpd.GeoDataFrame(
        s[["stop_name"]].copy(),
        geometry=gpd.points_from_xy(s.stop_lon, s.stop_lat), crs=WGS84).to_crs(METRIC)
    gp["hub"] = gp.stop_name.map(lambda n: hub_of(n, hubs))
    sg = sg.astype(float)
    share = sg.div(sg.sum(axis=1), axis=0)
    gp["dom"] = share.idxmax(axis=1)
    gp["domshare"] = share.max(axis=1)
    gp["ntrips"] = sg.sum(axis=1)
    gp["groups"] = [{k: int(v) for k, v in row.items() if v > 0} for _, row in sg.iterrows()]
    gp["routes"] = srt
    cbd = gpd.GeoSeries([Point(*CBD_CENTRE)], crs=WGS84).to_crs(METRIC).iloc[0]
    gp["cbd"] = gp.distance(cbd) < CBD_RADIUS_M
    gp["cls"] = np.where(gp.hub.notna(), "hub",
                np.where(gp.cbd, "cbd",
                np.where(gp.domshare >= DOMINANT_SHARE, gp.dom, "shared")))
    return gp


def pct(d):
    tot = sum(d.values())
    return " ".join(f"{k}:{round(100 * v / tot)}" for k, v in sorted(d.items(), key=lambda x: -x[1]))


def catchments(gp):
    """Voronoi cells around stops clipped to a walk radius: one per stop (cells)
    and dissolved by class (zones)."""
    env = box(*gp.total_bounds).buffer(3000)
    vor = voronoi_diagram(MultiPoint(list(gp.geometry)), envelope=env)
    cells = gpd.GeoDataFrame(geometry=list(vor.geoms), crs=METRIC)
    pp = gp[["cls", "geometry"]].reset_index(drop=True)
    pp["pid"] = range(len(pp))
    j = gpd.sjoin(cells, pp, predicate="contains", how="inner")
    j["geometry"] = [c.intersection(pp.geometry.iloc[i].buffer(CATCHMENT_M)) for c, i in zip(j.geometry, j.pid)]
    routes, groups = list(gp.routes), list(gp.groups)
    out = j[["pid", "cls", "geometry"]].copy()
    out["r"] = [" ".join(routes[i]) for i in out.pid]
    out["g"] = [pct(groups[i]) for i in out.pid]
    out["geometry"] = out.simplify(10)
    zones = j.dissolve(by="cls").reset_index()[["cls", "geometry"]]
    zones["geometry"] = zones.buffer(30).buffer(-30).simplify(15)
    return out, zones


def corridors(rt):
    """250 m bands around each route's and each group's paths, main and variant kept separate."""
    # Buffering each path and then unioning is ~70x faster than buffering the
    # unioned lines, and differs by well under 0.1% of the area.
    def bands(d):
        b = d.geometry.buffer(BAND_M)
        m = b[d.main.values].union_all()
        v = b.union_all().difference(m).buffer(-5).buffer(5)
        return m, (v if not v.is_empty and v.area > MIN_VARIANT_AREA_M2 else None)

    rb, gb = [], []
    for rn, d in rt.groupby("route_short_name"):
        m, v = bands(d)
        g = d.group.iloc[0]
        rb.append((rn, g, "main", m))
        if v is not None:
            rb.append((rn, g, "variant", v))
    for g, d in rt.groupby("group"):
        m, v = bands(d)
        gb.append((g, "main", m))
        if v is not None:
            gb.append((g, "variant", v))
    routebuf = gpd.GeoDataFrame(rb, columns=["route", "group", "kind", "geometry"], crs=METRIC)
    groupbuf = gpd.GeoDataFrame(gb, columns=["group", "kind", "geometry"], crs=METRIC)
    routebuf["geometry"] = routebuf.simplify(15)
    groupbuf["geometry"] = groupbuf.simplify(15)
    return routebuf, groupbuf


def stop_details(gp, st, all_stop_times, day_trips, r, all_routes):
    """Per-stop route trip counts (rc, e.g. '380:31 382:3') and other routes from
    any operator stopping there on the same day (other)."""
    out = gp[["stop_name", "cls", "ntrips", "routes", "geometry"]].copy()
    out["routes"] = out.routes.map(" ".join)
    rc = st.groupby(["stop_id", "route_short_name"]).size()
    out["rc"] = [" ".join(f"{k}:{int(v)}" for k, v in sorted(rc.loc[sid].items(), key=lambda x: route_key(x[0])))
                 for sid in out.index]
    others = day_trips[~day_trips.route_id.isin(set(r.route_id))].merge(
        all_routes[["route_id", "route_short_name"]], on="route_id")
    o = all_stop_times[all_stop_times.stop_id.isin(set(out.index))].merge(
        others[["trip_id", "route_short_name"]], on="trip_id")
    oth = o.groupby("stop_id").route_short_name.agg(rsort).to_dict()
    out["other"] = [" ".join(oth.get(i, [])) for i in out.index]
    return out


def hub_summary(gp, hub_cfg):
    """Weekday stop visits per group at each configured hub. All stops matching a
    hub (e.g. every UQ stop) count towards it."""
    hubs = []
    for h in hub_cfg:
        d = gp[gp.hub == h["name"]]
        if d.empty:
            continue
        agg = {}
        for x in d["groups"]:
            for k, v in x.items():
                agg[k] = agg.get(k, 0) + v
        if "at" in h:
            lat, lon = h["at"]
        else:
            c = d.to_crs(WGS84).geometry.union_all().centroid
            lat, lon = c.y, c.x
        hubs.append(dict(name=h["name"], short=h.get("short", h["name"]), lat=round(lat, 5), lon=round(lon, 5),
                         groups=dict(sorted(agg.items())),
                         routes=rsort(sum(d.routes, []))))
    return hubs


def group_summary(r, rtrips, gp, zones, hubs):
    gs = []
    for g, d in r.groupby("group"):
        rs = rsort(d.route_short_name)
        z = zones[zones.cls == g]
        gs.append(dict(
            group=g, routes=rs,
            trips=int(sum(rtrips.get(x, 0) for x in rs)),
            area_km2=round(float(z.area.sum()) / 1e6, 1) if len(z) else 0,
            own_stops=int((gp.cls == g).sum()),
            hub_visits={h["name"]: h["groups"][g] for h in hubs if g in h["groups"]},
        ))
    return gs


def add_anchors(groups, zones, overrides):
    """Where a group's hub spoke starts: a representative point of the largest part
    of its zone, or the centroid of all zones if it owns none. Config can pin one."""
    for g in groups:
        if g["group"] in overrides:
            lat, lon = overrides[g["group"]]
        else:
            z = zones[zones.cls == g["group"]]
            if len(z):
                parts = z.explode(index_parts=False)
                p = parts.geometry.iloc[int(parts.area.values.argmax())].representative_point()
            else:
                p = zones.geometry.union_all().centroid
            p = gpd.GeoSeries([p], crs=METRIC).to_crs(WGS84).iloc[0]
            lat, lon = p.y, p.x
        g["cx"], g["cy"] = round(lon, 5), round(lat, 5)
