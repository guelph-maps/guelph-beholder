from beholder.streets import city_street_norm, normalize_street


def test_long_form_source_and_osm_converge():
    # Guelph's source street is already OSM long form; both sides collapse the
    # same way, which is what makes the empty override table workable.
    assert city_street_norm("Cork Street West") == "CORK ST W"
    assert city_street_norm("Cork Street West") == normalize_street("Cork Street West")
    assert normalize_street("Silvercreek Parkway North") == "SILVERCREEK PKWY N"


def test_short_osm_spelling_still_matches():
    # A mapper writing the abbreviated form must still match the source.
    assert normalize_street("Cork St W") == city_street_norm("Cork Street West")


def test_unmapped_suffix_passes_through_identically():
    # Guelph has Glen / Walk / Run / Crossing streets, which the suffix table
    # deliberately leaves alone — identity on both sides is still a match.
    assert normalize_street("Dumbarton Glen") == city_street_norm("Dumbarton Glen")


def test_mc_prefix_glue():
    assert city_street_norm("Mc Cann St") == normalize_street("McCann Street")
    assert normalize_street("McCann Street") == "MCCANN ST"


def test_empty():
    assert normalize_street(None) == ""
    assert city_street_norm("") == ""
