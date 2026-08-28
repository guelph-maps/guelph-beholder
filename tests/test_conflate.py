from beholder.city import AddressPoint
from beholder.conflate import (CLEAN, COMBINED, MISSING, PRESENT, SEMICOLON,
                               conflate_points, split_combined)
from beholder.osm import OsmElement


def _point(apid, lat, lon, hn="100", unit="", street_norm="MAIN ST"):
    return AddressPoint(
        address_point_id=apid, address_full=f"{hn} Main Street", address_number=hn,
        housenumber_norm=hn, street_full="Main Street", street_norm=street_norm,
        unit=unit, unit_norm=unit.upper(), kind="unit" if unit else "civic",
        municipality="Guelph", ward="3", postcode="N1H 2X3", lat=lat, lon=lon,
    )


def _el(otype, oid, lat, lon, tags):
    return OsmElement(type=otype, id=oid, lat=lat, lon=lon, tags=tags)


ADDR = {"addr:housenumber": "100", "addr:street": "Main Street"}


def test_present_when_within_radius():
    p = _point(1, 43.545, -80.248)
    el = _el("node", 100, 43.545, -80.248, ADDR)
    [r] = conflate_points([p], [el], radius_m=100)
    assert r.status == PRESENT and r.osm_ref == "node/100"
    assert r.representation == "node" and r.match_form == CLEAN


def test_missing_when_beyond_radius():
    p = _point(1, 43.545, -80.248)
    el = _el("node", 100, 43.555, -80.248, ADDR)  # ~1.1 km north
    [r] = conflate_points([p], [el], radius_m=100)
    assert r.status == MISSING and r.osm_ref is None


def test_missing_when_street_differs():
    p = _point(1, 43.545, -80.248, street_norm="OAK ST")
    el = _el("node", 100, 43.545, -80.248, ADDR)
    [r] = conflate_points([p], [el], radius_m=100)
    assert r.status == MISSING


def test_representation_building_vs_node():
    p = _point(1, 43.545, -80.248)
    way = _el("way", 200, 43.545, -80.248, {**ADDR, "building": "yes"})
    [r] = conflate_points([p], [way], radius_m=100)
    assert r.representation == "building"


def test_far_twin_on_same_street_is_missing():
    near = _point(1, 43.545, -80.248)
    far = _point(2, 43.560, -80.248)
    el = _el("node", 100, 43.545, -80.248, ADDR)
    res = {r.address_point_id: r for r in conflate_points([near, far], [el], radius_m=100)}
    assert res[1].status == PRESENT and res[2].status == MISSING


def test_picks_nearest_candidate():
    p = _point(1, 43.545, -80.248)
    near = _el("node", 100, 43.5451, -80.248, ADDR)
    far = _el("node", 101, 43.5455, -80.248, ADDR)
    [r] = conflate_points([p], [far, near], radius_m=100)
    assert r.osm_ref == "node/100"


# --- the double-encoded-housenumber workaround ------------------------------

COMBINED_EL = {"addr:housenumber": "100-30", "addr:unit": "30",
               "addr:street": "Main Street"}


def test_civic_point_accepts_combined_housenumber():
    # Nothing in OSM carries bare "100" — only unit nodes written "100-30".
    # The civic address is accepted as found, and flagged.
    p = _point(1, 43.545, -80.248)
    el = _el("node", 100, 43.545, -80.248, COMBINED_EL)
    [r] = conflate_points([p], [el], radius_m=100)
    assert r.status == PRESENT and r.match_form == COMBINED


def test_clean_element_beats_a_nearer_combined_one():
    # Otherwise the "awaiting split" count inflates and osm_ref points at a
    # unit node when a plain civic object exists.
    p = _point(1, 43.545, -80.248)
    combined = _el("node", 100, 43.545, -80.248, COMBINED_EL)
    clean = _el("way", 200, 43.5452, -80.248, {**ADDR, "building": "yes"})
    [r] = conflate_points([p], [combined, clean], radius_m=100)
    assert r.osm_ref == "way/200" and r.match_form == CLEAN


def test_range_housenumber_is_not_read_as_a_unit():
    # "380-400 Waterloo Avenue" has no addr:unit backing the split, so it must
    # not answer to housenumber 380.
    p = _point(1, 43.545, -80.248, hn="380")
    el = _el("node", 100, 43.545, -80.248,
             {"addr:housenumber": "380-400", "addr:street": "Main Street"})
    [r] = conflate_points([p], [el], radius_m=100)
    assert r.status == MISSING


def test_unit_point_matches_its_own_door_only():
    unit30 = _point(1, 43.545, -80.248, unit="30")
    unit31 = _point(2, 43.545, -80.248, unit="31")
    el = _el("node", 100, 43.545, -80.248, COMBINED_EL)
    res = {r.address_point_id: r for r in conflate_points([unit30, unit31], [el], radius_m=100)}
    assert res[1].status == PRESENT and res[1].osm_ref == "node/100"
    assert res[2].status == MISSING


def test_unit_point_missing_when_only_the_civic_address_is_mapped():
    p = _point(1, 43.545, -80.248, unit="30")
    el = _el("node", 100, 43.545, -80.248, ADDR)
    [r] = conflate_points([p], [el], radius_m=100)
    assert r.status == MISSING


def test_unit_designator_case_is_normalized():
    p = _point(1, 43.545, -80.248, hn="650", unit="2b")
    el = _el("node", 100, 43.545, -80.248,
             {"addr:housenumber": "650-2B", "addr:unit": "2B",
              "addr:street": "Main Street"})
    [r] = conflate_points([p], [el], radius_m=100)
    assert r.status == PRESENT and r.match_form == COMBINED


def test_semicolon_list_answers_to_each_part():
    a = _point(1, 43.545, -80.248, hn="52A")
    b = _point(2, 43.545, -80.248, hn="52")
    el = _el("node", 100, 43.545, -80.248,
             {"addr:housenumber": "52A; 52B;52", "addr:street": "Main Street"})
    res = {r.address_point_id: r for r in conflate_points([a, b], [el], radius_m=100)}
    assert res[1].status == PRESENT and res[1].match_form == SEMICOLON
    assert res[2].status == PRESENT and res[2].match_form == SEMICOLON


def test_split_combined_keeps_a_lettered_civic_number():
    assert split_combined("645A-2", "2") == "645A"
    assert split_combined("380-400", "") is None
    assert split_combined("100-30", "5") is None
