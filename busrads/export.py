"""Compact GeoJSON/JSON writers for the site's data files."""
import json
from pathlib import Path

WGS84 = 4326


def _round(o, prec):
    if isinstance(o, float):
        return round(o, prec)
    if isinstance(o, list):
        return [_round(x, prec) for x in o]
    if isinstance(o, dict):
        return {k: _round(v, prec) for k, v in o.items()}
    return o


def write_geojson(gdf, path, prec=5):
    js = json.loads(gdf.to_crs(WGS84).to_json(drop_id=True))
    write_json(_round(js, prec), path, compact=True)


def write_json(obj, path, compact=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if compact:
            json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
        else:
            json.dump(obj, f, indent=1, ensure_ascii=False)
