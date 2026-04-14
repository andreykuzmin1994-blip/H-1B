from h1b_engine.utils import annualize_wage, normalize_employer_name, normalize_address


def test_annualize_hour():
    assert annualize_wage(50, "Hour") == 50 * 2080


def test_annualize_week():
    assert annualize_wage(1000, "Week") == 52000


def test_annualize_year_passthrough():
    assert annualize_wage(120000, "Year") == 120000


def test_annualize_handles_none_amount():
    assert annualize_wage(None, "Year") is None


def test_annualize_unknown_unit_defaults_to_annual():
    # Spec: falls back to amount when unit is unknown.
    assert annualize_wage(90000, "Semiannual") == 90000


def test_normalize_name_strips_suffixes_and_punctuation():
    assert normalize_employer_name("Acme Corp., Inc.") == "ACME"
    assert normalize_employer_name("FooBar Technologies LLC") == "FOOBAR"
    assert normalize_employer_name("  Quick Stop Petroleum Inc. ") == "QUICK STOP PETROLEUM"


def test_normalize_name_handles_empty():
    assert normalize_employer_name(None) == ""
    assert normalize_employer_name("") == ""


def test_normalize_address():
    out = normalize_address("1234 Memorial Dr.", "Decatur", "GA", "30032")
    assert "MEMORIAL" in out
    assert "DECATUR" in out
    assert "GA" in out
    assert "30032" in out
