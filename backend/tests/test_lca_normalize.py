from datetime import date

from h1b_engine.ingest.lca import normalize_row


def _raw(**overrides):
    base = {
        "CASE_NUMBER": "I-200-11111-123456",
        "CASE_STATUS": "CERTIFIED",
        "VISA_CLASS": "H-1B",
        "EMPLOYER_NAME": "Sunrise Convenience LLC",
        "EMPLOYER_ADDRESS1": "1234 Memorial Dr",
        "EMPLOYER_CITY": "Decatur",
        "EMPLOYER_STATE": "GA",
        "EMPLOYER_POSTAL_CODE": "30032",
        "NAICS_CODE": "447110",
        "SOC_CODE": "15-1252",
        "SOC_TITLE": "Software Developers",
        "JOB_TITLE": "Software Developer",
        "WAGE_RATE_OF_PAY_FROM": "15.00",
        "WAGE_UNIT_OF_PAY": "Hour",
        "PREVAILING_WAGE": "62000",
        "PW_UNIT_OF_PAY": "Year",
        "WORKSITE_CITY": "Decatur",
        "WORKSITE_STATE": "GA",
        "RECEIVED_DATE": "2024-01-01",
        "DECISION_DATE": "2024-02-01",
        "TOTAL_WORKER_POSITIONS": "1",
        "SECONDARY_ENTITY_BUSINESS_NAME": "",
    }
    base.update(overrides)
    return base


def test_normalize_row_basic():
    row = normalize_row(_raw(), fiscal_year=2024)
    assert row is not None
    assert row.case_number == "I-200-11111-123456"
    assert row.employer_state == "GA"
    assert row.soc_code == "15-1252"
    assert row.received_date == date(2024, 1, 1)
    assert row.fiscal_year == 2024
    assert row.wage_from == 15.0
    assert row.wage_unit == "Hour"


def test_normalize_row_rejects_missing_case_number():
    data = _raw()
    data["CASE_NUMBER"] = ""
    assert normalize_row(data) is None


def test_normalize_row_handles_alternate_columns():
    data = _raw()
    data["SOC_NAME"] = "Software Developers"
    del data["SOC_TITLE"]
    row = normalize_row(data)
    assert row is not None
    assert row.soc_title == "Software Developers"
