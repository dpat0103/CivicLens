from app.rag.resolver import known_place_names, resolve_places, strip_places


def names(db, query):
    return [p.name for p in resolve_places(db, query)]


def test_resolves_a_single_place_to_its_fips(db):
    places = resolve_places(db, "What is the median rent in Montclair?")
    assert [(p.name, p.fips) for p in places] == [("Montclair", "3401347500")]


def test_case_and_punctuation_do_not_matter(db):
    assert names(db, "how's JERSEY CITY doing??") == ["Jersey City"]


def test_places_returned_in_order_of_appearance(db):
    assert names(db, "Compare Trenton, Princeton and Camden") == ["Trenton", "Princeton", "Camden"]


def test_longest_name_wins_over_a_substring(db):
    # "Union City" contains "Union". Greedy matching would resolve the wrong
    # municipality, or both.
    assert names(db, "Tell me about Union City") == ["Union City"]


def test_both_names_resolve_when_both_are_present(db):
    assert names(db, "Compare Union City and Union") == ["Union City", "Union"]


def test_name_must_match_whole_words(db):
    # "Newark" must not be found inside "Newarkish".
    assert names(db, "Is Newarkish a place?") == []


def test_duplicate_names_resolve_to_distinct_fips_by_county(db):
    morris = resolve_places(db, "Rent in Washington Township (Morris County)")
    warren = resolve_places(db, "Rent in Washington Township, Warren County")
    assert [p.fips for p in morris] == ["3402777180"]
    assert [p.fips for p in warren] == ["3404177240"]
    assert morris[0].county == "Morris"


def test_both_duplicates_can_be_compared(db):
    places = resolve_places(
        db, "Compare Franklin Township (Somerset County) and Franklin Township (Hunterdon County)")
    assert [p.fips for p in places] == ["3403524990", "3401924840"]


def test_ambiguous_bare_name_resolves_to_nothing_rather_than_guessing(db):
    # Several municipalities share this name. Picking one would answer about
    # the wrong town with full confidence, so nothing is resolved.
    assert names(db, "What is the median rent in Washington Township?") == []
    assert names(db, "Tell me about Franklin Township") == []


def test_known_place_names_is_sorted_and_complete(db):
    known = known_place_names(db)
    assert known == sorted(known)
    assert len(known) == 15
    assert "Washington Township (Warren County)" in known


def test_strip_places_removes_names_that_contain_metric_words(db):
    query = "Compare Princeton and Trenton"
    cleaned = strip_places(query, resolve_places(db, query))
    assert "rent" not in cleaned
    assert "compare" in cleaned
