"""Depot route lists (depots/<id>.txt) and their display config (depots/<id>.json)."""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROUTE_RE = re.compile(r"(N?\d+)")


def route_key(r):
    """Sort route numbers the way drivers read them: 61 < 199 < 380 < N385."""
    return (len(r), r)


def group_of(route):
    """Prefix group of a route number: 380 -> 38x, N385 -> 38x."""
    return route.lstrip("N")[:2] + "x"


def parse_route_list(text):
    """Route numbers from a depot list: one per line after a header line.

    Suffixes such as '445 Ex' or '783 OAKLEIGH' are allowed; only the leading
    route number (N-prefixed night routes included) is kept.
    """
    found = set()
    for line in text.splitlines()[1:]:
        m = ROUTE_RE.match(line.strip())
        if m:
            found.add(m.group(1))
    return sorted(found, key=route_key)


def in_main_feed(route):
    """7xx (school runs) and 9xx (specials) aren't Brisbane routes in the main feed;
    the 7xx numbers there belong to the Gold Coast."""
    return route.lstrip("N")[0] not in "79"


@dataclass
class Depot:
    id: str
    name: str
    routes: list  # every number on the list, including ones not in the feed
    hubs: list = field(default_factory=list)
    anchors: dict = field(default_factory=dict)
    families: list = field(default_factory=list)
    areas: dict = field(default_factory=dict)
    places: list = field(default_factory=list)

    @property
    def feed_routes(self):
        return [r for r in self.routes if in_main_feed(r)]


def load_depot(depots_dir, depot_id):
    d = Path(depots_dir)
    routes = parse_route_list((d / f"{depot_id}.txt").read_text(encoding="utf-8"))
    cfg_path = d / f"{depot_id}.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    return Depot(
        id=depot_id,
        name=cfg.get("name", depot_id.title()),
        routes=routes,
        hubs=cfg.get("hubs", []),
        anchors=cfg.get("anchors", {}),
        families=cfg.get("families", []),
        areas=cfg.get("areas", {}),
        places=cfg.get("places", []),
    )


def depot_ids(depots_dir):
    return sorted(p.stem for p in Path(depots_dir).glob("*.txt"))
