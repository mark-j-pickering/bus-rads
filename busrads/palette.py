"""Colours for the "All routes" view: one hue family per hundred, a different
shade for each prefix group. Depot views use the hand-picked colours in the
site's CSS instead, so neighbouring zones within a depot stay distinct."""
import colorsys

from .depots import route_key

# hundreds digit ("0" = routes under 100) -> (hue in degrees, saturation)
FAMILIES = {
    "1": (32, 0.70),    # amber / orange
    "2": (140, 0.50),   # green
    "3": (214, 0.60),   # blue
    "4": (352, 0.62),   # red / rose
    "5": (278, 0.45),   # violet
    "0": (200, 0.12),   # slate grey
}
HUE_SPREAD = 26  # degrees across a family, so shades differ in hue as well as lightness
# Lightness steps, cycled so consecutive prefixes (often neighbours on the map) differ.
LIGHT_STEPS = [0.34, 0.52, 0.42, 0.60, 0.38, 0.48, 0.56, 0.30]
DARK_LIFT = 0.18  # dark theme: same colours, lighter, to read on the dark ground


def hundred(group):
    """'38x' -> '3'; one- and two-digit route groups ('29') -> '0'."""
    return group[0] if group.endswith("x") else "0"


def _hex(h, l, s):
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, max(0, min(1, l)), s)
    return "#%02x%02x%02x" % tuple(round(v * 255) for v in (r, g, b))


def hundreds_palette(groups):
    """{"light": {group: "#rrggbb"}, "dark": {...}} for the given prefix groups."""
    light, dark = {}, {}
    by_family = {}
    for g in sorted(groups, key=route_key):
        by_family.setdefault(hundred(g), []).append(g)
    for fam, gs in by_family.items():
        hue, sat = FAMILIES.get(fam, (0, 0))
        n = len(gs)
        for i, g in enumerate(sorted(gs, key=lambda x: x.lstrip("N").zfill(3))):
            h = hue + (HUE_SPREAD * (i / (n - 1) - 0.5) if n > 1 else 0)
            l = LIGHT_STEPS[i % len(LIGHT_STEPS)]
            light[g] = _hex(h, l, sat)
            dark[g] = _hex(h, l + DARK_LIFT, sat)
    return {"light": light, "dark": dark}
