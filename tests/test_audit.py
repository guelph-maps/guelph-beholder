from beholder.audit import AuditPolicy, is_campaign_only, issues_for
from beholder.city import AddressPoint
from beholder.conflate import COMBINED, MISSING, PRESENT, conflate_points
from beholder.osm import OsmElement

POLICY = AuditPolicy(far_match_m=40.0, deprecated_tags=("addr:province",))


def _point(hn="100", unit="", street="Main Street", postcode="N1H 2X3",
           muni="Guelph", lat=43.545, lon=-80.248, apid=1):
    return AddressPoint(
        address_point_id=apid, address_full=f"{hn} {street}", address_number=hn,
        housenumber_norm=hn, street_full=street, street_norm=street.upper()
        .replace("STREET", "ST").replace("  ", " ").strip(),
        unit=unit, unit_norm=unit.upper(), kind="unit" if unit else "civic",
        municipality=muni, ward="3", postcode=postcode, lat=lat, lon=lon,
    )


def _el(tags, lat=43.545, lon=-80.248, otype="node", oid=1):
    return OsmElement(type=otype, id=oid, lat=lat, lon=lon, tags=tags)


GOOD = {"addr:housenumber": "100", "addr:street": "Main Street",
        "addr:city": "Guelph", "addr:postcode": "N1H 2X3"}


def _issues(point_kw=None, tags=None, distance=0.0, match_count=1):
    """Audit a correct address with `tags` layered on top; a None value drops
    that tag from the element."""
    p = _point(**(point_kw or {}))
    merged = {**GOOD, **(tags or {})}
    el = _el({k: v for k, v in merged.items() if v is not None})
    return issues_for(p, el, distance, match_count, POLICY)


def test_a_correct_address_has_no_issues():
    assert _issues() == ()


def test_postcode_missing_mismatch_and_format():
    assert "postcode_missing" in _issues(tags={"addr:postcode": None})
    assert "postcode_mismatch" in _issues(tags={"addr:postcode": "N1G 4W4"})
    assert "postcode_format" in _issues(tags={"addr:postcode": "N1H2X3"})


def test_postcode_mismatch_beats_format():
    # A wrong postcode that is also unformatted is reported as wrong, not ugly.
    codes = _issues(tags={"addr:postcode": "N1G4W4"})
    assert "postcode_mismatch" in codes and "postcode_format" not in codes


def test_a_source_without_a_postcode_is_never_flagged():
    codes = _issues(point_kw={"postcode": ""}, tags={"addr:postcode": None})
    assert not [c for c in codes if c.startswith("postcode")]


def test_city_missing_and_mismatch():
    assert "city_missing" in _issues(tags={"addr:city": None})
    assert "city_mismatch" in _issues(tags={"addr:city": "Township of Puslinch"})


def test_city_is_compared_to_the_sources_own_place_not_to_guelph():
    # The 75 township rows legitimately say something other than "Guelph";
    # comparing against a constant turned 1 real disagreement into 74 false ones.
    codes = _issues(point_kw={"muni": "Guelph/Eramosa Twp"},
                    tags={"addr:city": "Guelph/Eramosa Twp"})
    assert "city_mismatch" not in codes


def test_street_spelling_fires_only_when_the_literals_differ():
    assert "street_spelling" in _issues(tags={"addr:street": "Main St"})
    assert "street_spelling" not in _issues(tags={"addr:street": "Main Street"})
    # A different street entirely is not a spelling disagreement — it would not
    # have matched in the first place.
    assert "street_spelling" not in _issues(tags={"addr:street": "Oak Street"})


def test_far_match_uses_the_policy_threshold():
    assert "far_match" not in _issues(distance=39.0)
    assert "far_match" in _issues(distance=41.0)


def test_duplicate_osm_needs_more_than_one_element():
    assert "duplicate_osm" not in _issues(match_count=1)
    assert "duplicate_osm" in _issues(match_count=2)


def test_civic_point_on_an_object_carrying_a_unit():
    assert "civic_on_unit_object" in _issues(tags={"addr:unit": "5"})
    assert "civic_on_unit_object" not in _issues(point_kw={"unit": "5"},
                                                tags={"addr:unit": "5"})


def test_deprecated_tags_come_from_policy():
    assert "deprecated_addr_province" in _issues(tags={"addr:province": "Ontario"})
    assert issues_for(_point(), _el({**GOOD, "addr:province": "Ontario"}), 0.0, 1,
                      AuditPolicy(deprecated_tags=())) == ()


def test_issues_are_sorted_so_the_stored_string_is_stable():
    codes = _issues(tags={"addr:province": "Ontario", "addr:postcode": "N1G 4W4"},
                    distance=99.0)
    assert list(codes) == sorted(codes)


def test_campaign_only_points_are_not_map_flagged():
    assert is_campaign_only(["deprecated_addr_province"]) is True
    assert is_campaign_only(["deprecated_addr_province", "far_match"]) is False
    assert is_campaign_only([]) is False


# --- integration through conflate -------------------------------------------

def test_missing_points_carry_no_issues():
    p = _point()
    [r] = conflate_points([p], [], radius_m=100, policy=POLICY)
    assert r.status == MISSING and r.issues == () and r.match_count == 0


def test_combined_matches_do_not_count_as_duplicates():
    # 30 unit nodes written "100-1".."100-30" are 30 doors, not 30 duplicates
    # of the civic address.
    p = _point()
    els = [_el({"addr:housenumber": f"100-{i}", "addr:unit": str(i),
                "addr:street": "Main Street", "addr:city": "Guelph",
                "addr:postcode": "N1H 2X3"}, oid=100 + i) for i in range(1, 31)]
    [r] = conflate_points([p], els, radius_m=100, policy=POLICY)
    assert r.status == PRESENT and r.match_form == COMBINED
    assert r.match_count == 0 and "duplicate_osm" not in r.issues


def test_a_node_inside_an_addressed_building_is_a_duplicate():
    p = _point()
    node = _el(GOOD, oid=1)
    way = _el({**GOOD, "building": "yes"}, lat=43.5451, otype="way", oid=2)
    [r] = conflate_points([p], [node, way], radius_m=100, policy=POLICY)
    assert r.match_count == 2 and "duplicate_osm" in r.issues
