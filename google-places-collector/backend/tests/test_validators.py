import pytest
from app.services.errors import InputValidationError
from app.utils.validators import (
    build_text_query,
    category_to_included_type,
    clean_category,
    clean_location,
    clean_radius_km,
)


def test_location_accepts_city_area_pincode_and_address():
    assert clean_location("Ahmedabad") == "Ahmedabad"
    assert clean_location("  Satellite, Ahmedabad ") == "Satellite, Ahmedabad"
    assert clean_location("380015") == "380015"
    assert clean_location("SG Highway, Ahmedabad") == "SG Highway, Ahmedabad"
    assert clean_location("Navrangpura") == "Navrangpura"


def test_location_rejects_coordinates_and_empty():
    with pytest.raises(InputValidationError):
        clean_location("23.0225, 72.5714")
    with pytest.raises(InputValidationError):
        clean_location("23.0225 72.5714")
    with pytest.raises(InputValidationError):
        clean_location(" ")
    with pytest.raises(InputValidationError):
        clean_location("x" * 201)


def test_category_is_free_text():
    assert clean_category("  Petrol   Pump ") == "Petrol Pump"
    assert clean_category("College") == "College"
    with pytest.raises(InputValidationError):
        clean_category("   ")


def test_text_query_joins_category_keyword_and_location():
    assert build_text_query("Hotel", "Ahmedabad", None) == "Hotel Ahmedabad"
    assert build_text_query("School", "Ahmedabad", "primary") == "School primary Ahmedabad"
    assert build_text_query("Office", "SG Highway, Ahmedabad", None) == "Office SG Highway, Ahmedabad"


def test_nearby_type_is_a_generic_token_not_a_category_map():
    assert category_to_included_type("Hotel") == "hotel"
    assert category_to_included_type("Petrol Pump") == "petrol_pump"
    assert category_to_included_type("petrol_pump") != "gas_station"


def test_radius_bounds():
    assert clean_radius_km(None) == 5
    assert clean_radius_km(1.5) == 1.5
    with pytest.raises(InputValidationError):
        clean_radius_km(0)
    with pytest.raises(InputValidationError):
        clean_radius_km(80)
