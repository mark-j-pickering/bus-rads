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
    """Prefix group of a route number: 380 -> 38x, N385 -> 38x.

    One- and two-digit routes (29, 61) have no prefix to share, so each is
    its own group, named by its number."""
    n = route.lstrip("N")
    return n[:2] + "x" if len(n) >= 3 else n


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
    n = route.lstrip("N")
    return not (len(n) >= 3 and n[0] in "79")


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
    """Every depot with a route list, in the order the site lists them: by the
    optional "order" in its config, then by id."""
    d = Path(depots_dir)

    def order(i):
        cfg = d / f"{i}.json"
        return json.loads(cfg.read_text(encoding="utf-8")).get("order", 999) if cfg.exists() else 999

    return sorted((p.stem for p in d.glob("*.txt")), key=lambda i: (order(i), i))


def _family_order(label):
    """'100s · south-east' sorts by its hundreds; anything else (inner-city links) goes last."""
    m = re.match(r"(\d+)s\b", label)
    return (int(m.group(1)) if m else 10_000, label)


def combine(depots, id="all", name="All depots"):
    """One selection covering several depots. A route on more than one list
    appears once; hubs, anchors, families, areas and suburb labels are merged."""
    routes = sorted({r for d in depots for r in d.routes}, key=route_key)
    hubs, seen = [], set()
    anchors, places, place_names = {}, [], set()
    fam_groups, areas = {}, {}
    assigned = set()
    for d in depots:
        for h in d.hubs:
            if h["name"] not in seen:
                seen.add(h["name"])
                hubs.append(h)
        for g, a in d.anchors.items():
            anchors.setdefault(g, a)
        for p in d.places:
            if p[0] not in place_names:
                place_names.add(p[0])
                places.append(p)
        for f in d.families:
            gs = fam_groups.setdefault(f["label"], [])
            for g in f["groups"]:
                if g not in assigned:   # a group sits in the first family that lists it
                    assigned.add(g)
                    gs.append(g)
        for g, text in d.areas.items():
            if text not in areas.setdefault(g, []):
                areas[g].append(text)
    families = [{"label": lab, "groups": sorted(gs, key=route_key)}
                for lab, gs in sorted(fam_groups.items(), key=lambda kv: _family_order(kv[0])) if gs]
    return Depot(id=id, name=name, routes=routes, hubs=hubs, anchors=anchors, families=families,
                 areas={g: "; ".join(t) for g, t in areas.items()}, places=places)


# Words that describe the service rather than the place, stripped from route-name endpoints.
_SERVICE_WORDS = re.compile(
    r"\b(Express|Rocket|Bullet|NightLink|Shuttle|StationLink|Loop|busway|Hail 'n' Ride|"
    r"Anti-Clockwise|Clockwise|Community Bus\s*\d*)", re.I)
_CITY = {"city", "city/valley", "valley", "cbd"}


def auto_area(long_names, top=3):
    """A short area line from a group's route names when no depot describes it:
    the most common non-City endpoints, e.g. 'Parkinson, Griffith University, Sunnybank Hills'."""
    counts, order = {}, []
    for name in long_names:
        main = re.split(r"\s+via\s+", name, maxsplit=1)[0]
        for end in main.split(" - "):
            place = re.sub(r"\s+", " ", _SERVICE_WORDS.sub("", re.sub(r"[()]", " ", end))).strip(" ,")
            if not place or place.lower() in _CITY:
                continue
            if place not in counts:
                order.append(place)
            counts[place] = counts.get(place, 0) + 1
    best = sorted(order, key=lambda p: -counts[p])[:top]
    return ", ".join(best) if best else (re.sub(r"\s*\(.*?\)", "", long_names[0]) if long_names else "")


def all_routes_selection(sel, routes, cfg):
    """The "All routes" view: every route of the operator, with hubs, anchors and
    suburb labels from all depots, families by hundreds, and area descriptions
    from depot configs where they exist, generated from route names otherwise.

    routes: routes.txt rows (route_short_name, route_long_name) for the operator."""
    base = combine(sel, id="all", name=cfg.get("name", "All routes"))
    numbers = sorted(routes.route_short_name, key=route_key)
    names = routes.groupby(routes.route_short_name.map(group_of)).route_long_name.agg(list).to_dict()
    groups = sorted(names, key=route_key)
    labels = cfg.get("families", {})
    fam = {}
    for g in groups:
        h = g[0] if g.endswith("x") else "0"
        fam.setdefault(h, []).append(g)
    order = sorted(fam, key=lambda h: (h == "0", h))   # 100s..500s, then under 100
    families = [{"label": labels.get(h, f"{h}00s" if h != "0" else "Under 100"),
                 "groups": sorted(fam[h], key=route_key)} for h in order]
    areas = {g: base.areas.get(g) or auto_area(names[g]) for g in groups}
    return Depot(id="all", name=base.name, routes=numbers, hubs=base.hubs, anchors=base.anchors,
                 families=families, areas=areas, places=base.places)
