from app.services.deduplication import dedupe_places, fallback_key, place_key
from app.services.normalized import NormalizedPlace
from app.services.result_filters import FilterSpec, apply_filters, sort_items


def _place(**kwargs) -> NormalizedPlace:
    base = dict(
        google_place_id="p1",
        name="Alpha",
        address="1 Road",
        latitude=23.0,
        longitude=72.0,
        rating=4.0,
        review_count=10,
        phone="111",
        website="https://a.example",
        business_status="OPERATIONAL",
        types=["hotel"],
        position=1,
    )
    base.update(kwargs)
    return NormalizedPlace(**base)


def test_dedupe_by_google_place_id():
    first = _place(google_place_id="same", name="One")
    second = _place(google_place_id="same", name="Different")
    third = _place(google_place_id="other", name="Two")
    unique, removed = dedupe_places([first, second, third])
    assert removed == 1
    assert [item.name for item in unique] == ["One", "Two"]
    assert place_key(first).startswith("gid:")


def test_dedupe_fallback_name_address_rounded_coordinates():
    first = _place(
        google_place_id=None,
        name="City Gym",
        address="12 Road, Ahmedabad",
        latitude=23.02251,
        longitude=72.57141,
    )
    second = _place(
        google_place_id=None,
        name="city  gym",
        address="12 road ahmedabad",
        latitude=23.02254,
        longitude=72.57144,
    )
    third = _place(
        google_place_id=None,
        name="City Gym",
        address="12 Road, Ahmedabad",
        latitude=23.03001,
        longitude=72.57141,
    )
    assert fallback_key(first.name, first.address, first.latitude, first.longitude) == fallback_key(
        second.name, second.address, second.latitude, second.longitude
    )
    unique, removed = dedupe_places([first, second, third])
    assert removed == 1
    assert len(unique) == 2


def test_filters_rating_reviews_status_type_contact_and_distance():
    near = _place(name="Near", rating=4.8, review_count=50, distance_meters=400, types=["gym"])
    far = _place(
        google_place_id="p2",
        name="Far Cafe",
        rating=3.2,
        review_count=2,
        distance_meters=9000,
        website=None,
        phone=None,
        business_status="CLOSED_TEMPORARILY",
        types=["cafe"],
        position=2,
    )
    kept = apply_filters(
        [near, far],
        FilterSpec(min_rating=4, min_reviews=10, business_status="OPERATIONAL", type_contains="gym"),
    )
    assert [item.name for item in kept] == ["Near"]
    website_only = apply_filters([near, far], FilterSpec(has_website=True, has_phone=True, has_both=True))
    assert [item.name for item in website_only] == ["Near"]
    local = apply_filters([near, far], FilterSpec(max_distance_km=1))
    assert [item.name for item in local] == ["Near"]
    named = apply_filters([near, far], FilterSpec(keyword="cafe"))
    assert [item.name for item in named] == ["Far Cafe"]


def test_sort_orders_and_keeps_missing_values_last():
    low = _place(name="Bravo", rating=3, review_count=5, distance_meters=100, position=1)
    high = _place(google_place_id="p2", name="alpha", rating=5, review_count=50, distance_meters=300, position=2)
    blank = _place(
        google_place_id="p3",
        name=None,
        rating=None,
        review_count=None,
        distance_meters=None,
        position=3,
    )
    assert [item.rating for item in sort_items([low, blank, high], "rating_desc")] == [5, 3, None]
    assert [item.rating for item in sort_items([high, blank, low], "rating_asc")] == [3, 5, None]
    assert [item.review_count for item in sort_items([low, high, blank], "reviews_desc")] == [50, 5, None]
    assert [item.name for item in sort_items([low, high, blank], "name_asc")] == ["alpha", "Bravo", None]
    assert [item.name for item in sort_items([low, high, blank], "name_desc")] == ["Bravo", "alpha", None]
    assert [item.distance_meters for item in sort_items([high, blank, low], "distance_asc")] == [100, 300, None]
    assert [item.position for item in sort_items([high, low], "position_asc")] == [1, 2]
