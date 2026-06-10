from glasshouse.ingest.doj_fcpa import parse_link_text


def test_us_v_docket_pattern():
    assert parse_link_text("U.S. v. BAE Systems plc: Docket No. 10-CR-035-JDB") == \
        ("BAE Systems plc", 2010)


def test_in_re_paren_year_pattern():
    assert parse_link_text("In re AAR Corp. (2024)") == ("AAR Corp", 2024)


def test_united_states_v_pattern():
    company, year = parse_link_text(
        "United States v. Goldman Sachs Group, Inc.: Docket No. 20-CR-437")
    assert company == "Goldman Sachs Group, Inc."
    assert year == 2020


def test_docket_year_window():
    # 92-CR → 1992 (pre-2000 docket numbers)
    _, year = parse_link_text("U.S. v. Example Corp: Docket No. 92-CR-087")
    assert year == 1992


def test_footer_navigation_rejected():
    assert parse_link_text("Privacy") is None
    assert parse_link_text("Signup for Email Updates") is None
    assert parse_link_text("someone@justice.gov") is None
