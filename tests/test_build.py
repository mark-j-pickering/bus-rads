import datetime as dt

import pandas as pd
import pytest

from busrads.depots import group_of, in_main_feed, parse_route_list
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
