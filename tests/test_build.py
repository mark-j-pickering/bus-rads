import datetime as dt

import pandas as pd
import pytest

from busrads.depots import Depot, combine, group_of, in_main_feed, parse_route_list
from busrads.feed import BuildError, active_services, pick_service_day, select_routes


def test_parse_route_list_keeps_leading_number():
    text = "Routes serviced by Somewhere\n\n445\n445 Ex\n706 AM\n783 OAKLEIGH\nN385\n61\n\n"
    assert parse_route_list(text) == ["61", "445", "706", "783", "N385"]


def test_header_line_is_skipped_even_if_numeric():
    assert parse_route_list("199\n380\n") == ["380"]


def test_group_and_feed_filter():
    assert group_of("380") == "38x"
    assert group_of("N385") == "38x"
    assert group_of("29") == "29"
    assert group_of("61") == "61"
    assert group_of("N61") == "61"
    assert not in_main_feed("706")
    assert not in_main_feed("922")
    assert in_main_feed("N385")
    assert in_main_feed("77")     # Eight Mile Plains - Chermside, not a school run
    assert in_main_feed("9")


def routes(*rows):
    return pd.DataFrame(rows, columns=["route_id", "route_short_name", "route_type"])


def test_select_routes_picks_majority_operator():
    r = routes(("380-5146", "380", "3"), ("411-5146", "411", "3"),
               ("411-5171", "411", "3"), ("411-9999", "411", "2"))
    sel, op = select_routes(r, ["380", "411"])
    assert op == "5146"
    assert sorted(sel.route_id) == ["380-5146", "411-5146"]


def test_select_routes_fails_on_missing_route():
    r = routes(("380-5146", "380", "3"), ("411-5146", "411", "3"), ("999-5171", "999", "3"))
    with pytest.raises(BuildError, match="999"):
        select_routes(r, ["380", "411", "999"])


def calendar(*rows):
    cols = ["service_id", "monday", "tuesday", "wednesday", "thursday", "friday",
            "saturday", "sunday", "start_date", "end_date"]
    return pd.DataFrame(rows, columns=cols)


def test_active_services_applies_exceptions():
    cal = calendar(("wk", "1", "1", "1", "1", "1", "0", "0", "20261001", "20261231"))
    cd = pd.DataFrame([("wk", "20261014", "2"), ("extra", "20261014", "1")],
                      columns=["service_id", "date", "exception_type"])
    assert active_services(cal, cd, dt.date(2026, 10, 14)) == {"extra"}
    assert active_services(cal, cd, dt.date(2026, 10, 15)) == {"wk"}


def test_pick_service_day_prefers_busiest_then_wednesday():
    cal = calendar(("wk", "1", "1", "1", "1", "1", "0", "0", "20261010", "20261231"))
    cd = pd.DataFrame(columns=["service_id", "date", "exception_type"])
    trips = pd.DataFrame({"service_id": ["wk", "wk"]})
    # Sat 10 Oct start: Tue 13, Wed 14, Thu 15 tie, so Wednesday wins.
    assert pick_service_day(dt.date(2026, 10, 10), cal, cd, trips) == dt.date(2026, 10, 14)
    # No service on Wed 14th: the next Wednesday still wins the tie.
    cd = pd.DataFrame([("wk", "20261014", "2")], columns=["service_id", "date", "exception_type"])
    assert pick_service_day(dt.date(2026, 10, 10), cal, cd, trips) == dt.date(2026, 10, 21)
    # A busier day beats Wednesday.
    cd = pd.DataFrame([("extra", "20261015", "1")], columns=["service_id", "date", "exception_type"])
    trips = pd.DataFrame({"service_id": ["wk", "extra"]})
    assert pick_service_day(dt.date(2026, 10, 10), cal, cd, trips) == dt.date(2026, 10, 15)


def test_combine_merges_depots():
    a = Depot(id="a", name="A", routes=["199", "380", "445"],
              hubs=[{"name": "UQ", "match": "uq"}], anchors={"40x": [1, 2]},
              families=[{"label": "300s · north-west", "groups": ["38x"]},
                        {"label": "Inner-city links", "groups": ["19x"]}],
              areas={"19x": "West End ferry link", "38x": "The Gap"},
              places=[["City", 1, 2], ["The Gap", 3, 4]])
    b = Depot(id="b", name="B", routes=["197", "209", "380"],
              hubs=[{"name": "UQ", "match": "uq"}, {"name": "Carindale", "match": "carindale"}],
              families=[{"label": "200s · east", "groups": ["20x"]},
                        {"label": "Inner-city links", "groups": ["19x"]}],
              areas={"19x": "South Brisbane loop", "20x": "Carindale"},
              places=[["City", 1, 2], ["Carina", 5, 6]])
    c = combine([a, b])
    assert c.id == "all"
    assert c.routes == ["197", "199", "209", "380", "445"]          # 380 once
    assert [h["name"] for h in c.hubs] == ["UQ", "Carindale"]
    assert [f["label"] for f in c.families] == ["200s · east", "300s · north-west", "Inner-city links"]
    assert c.families[2]["groups"] == ["19x"]                          # not listed twice
    assert c.areas["19x"] == "West End ferry link; South Brisbane loop"
    assert [p[0] for p in c.places] == ["City", "The Gap", "Carina"]
    assert c.anchors == {"40x": [1, 2]}


def test_hundreds_palette():
    from busrads.palette import hundreds_palette
    groups = ["10x", "11x", "12x", "20x", "21x", "38x", "41x", "29", "61"]
    p = hundreds_palette(groups)
    assert set(p["light"]) == set(p["dark"]) == set(groups)
    assert len(set(p["light"].values())) == len(groups)     # every group its own shade
    assert hundreds_palette(list(reversed(groups))) == p      # deterministic, order-independent


def test_auto_area():
    from busrads.depots import auto_area
    assert auto_area(["Parkinson - City", "Parkinson - City via Hellawell Rd",
                      "Sunnybank Hills - City Rocket"]) == "Parkinson, Sunnybank Hills"
    assert auto_area(["City Loop (Clockwise)"]) == "City Loop"
