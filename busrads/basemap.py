"""The drawn basemap: roads, rail and river traced from every bus, rail and ferry
shape in the feed. A stand-in until the site uses real map tiles."""
import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry import LineString, box

from .analysis import METRIC, WGS84
from .export import write_json

BOUNDS = (152.80, -27.62, 153.23, -27.33)   # what's drawn: Moggill to Wynnum
CLIP = (152.75, -27.65, 153.26, -27.30)     # points read, a little wider
LAYERS = [("3", "roads", 12), ("2", "rail", 15), ("4", "river", 20)]  # route_type, key, simplify m


def _round(o):
    if isinstance(o, (list, tuple)):
        return [_round(x) for x in o]
    return round(o, 4) if isinstance(o, float) else o


def build_basemap(feed, path):
    t = feed.trips[["route_id", "shape_id"]].drop_duplicates("shape_id").merge(
        feed.routes[["route_id", "route_type"]], on="route_id")
    keep = set(t.shape_id)
    w, s, e, n = CLIP
    parts = []
    for ch in pd.read_csv(feed.dir / "shapes.txt", chunksize=500_000,
                          usecols=["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"],
                          dtype={"shape_id": str, "shape_pt_lat": "float32",
                                 "shape_pt_lon": "float32", "shape_pt_sequence": "int32"}):
        parts.append(ch[ch.shape_pt_lon.between(w, e) & ch.shape_pt_lat.between(s, n) & ch.shape_id.isin(keep)])
    sh = pd.concat(parts).sort_values(["shape_id", "shape_pt_sequence"])
    rows = [(k, LineString(list(zip(v.shape_pt_lon.astype(float), v.shape_pt_lat.astype(float)))))
            for k, v in sh.groupby("shape_id") if len(v) > 1]
    g = gpd.GeoDataFrame(rows, columns=["shape_id", "geometry"], crs=WGS84).merge(
        t[["shape_id", "route_type"]], on="shape_id").to_crs(METRIC)
    g["geometry"] = g.simplify(10)
    bb = gpd.GeoSeries([box(*BOUNDS)], crs=WGS84).to_crs(METRIC).iloc[0]
    out = {}
    for typ, key, tol in LAYERS:
        u = shapely.union_all(g[g.route_type == typ].geometry.values).intersection(bb).simplify(tol)
        geom = gpd.GeoSeries([u], crs=METRIC).to_crs(WGS84).iloc[0]
        js = shapely.geometry.mapping(geom)
        out[key] = {"type": js["type"], "coordinates": _round(js["coordinates"])}
    write_json(out, path, compact=True)
