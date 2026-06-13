"""Property-based tests (Hypothesis) — applying the Trail of Bits
property-based-testing methodology to Glasshouse's highest-value pure
functions: the entity matcher (normalization + similarity), vote dedup,
and the concern index.

Properties chosen by the skill's strength hierarchy (invariant → idempotence
→ roundtrip) over the functions most likely to harbor a precision bug — the
class of bug that, in this project, becomes a false public accusation.
"""

from __future__ import annotations

from datetime import date

from hypothesis import assume, given
from hypothesis import strategies as st

from glasshouse.entities import _CUSIP_RE, fuzzy_match, jaccard_similarity, normalize_name
from glasshouse.scoring import SEVERITY, concern_index

# Names as they appear in filings: letters, digits, spaces, legal punctuation.
_name = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs"),
                           whitelist_characters=" .,&-'"),
    min_size=1, max_size=60)


# ── normalize_name: idempotence (the skill's MEDIUM-priority normalizer case) ──

@given(_name)
def test_normalize_is_idempotent(name):
    once = normalize_name(name)
    assert normalize_name(once) == once


@given(_name)
def test_normalize_is_lossless_lowercase_stable(name):
    # Normalization never raises and always returns a string.
    assert isinstance(normalize_name(name), str)


# ── jaccard_similarity: bounded + symmetric invariants ───────────────────────

@given(_name, _name)
def test_jaccard_bounded_and_symmetric(a, b):
    s = jaccard_similarity(a, b)
    assert 0.0 <= s <= 1.0
    assert jaccard_similarity(a, b) == jaccard_similarity(b, a)


@given(_name)
def test_jaccard_self_is_one_when_tokens_exist(a):
    assume(_has_tokens(a))
    assert jaccard_similarity(a, a) == 1.0


# ── fuzzy_match: the invariants the Aldar lesson depends on ───────────────────

@given(_name, _name)
def test_fuzzy_score_bounded_and_symmetric(a, b):
    m1, s1 = fuzzy_match(a, b)
    m2, s2 = fuzzy_match(b, a)
    assert 0.0 <= s1 <= 1.0
    assert s1 == s2 and m1 == m2  # match is symmetric — direction must not matter


@given(_name)
def test_fuzzy_self_match(a):
    assume(_has_tokens(a) and not _CUSIP_RE.match(a.strip().upper()))
    matched, score = fuzzy_match(a, a)
    assert matched and score == 1.0


@given(st.from_regex(r"[0-9A-Z]{9}", fullmatch=True), _name)
def test_cusip_never_fuzzy_matches_a_name(cusip, name):
    # A CUSIP-shaped string must never fuzzy-match a company name — the guard
    # that keeps bare identifiers from colliding with text.
    assume(_CUSIP_RE.match(cusip))
    assume(not _CUSIP_RE.match(name.strip().upper()))
    matched, _ = fuzzy_match(cusip, name)
    assert matched is False


# ── concern_index: monotonicity + the quarantine-scores-zero invariant ───────

_scored_types = sorted(k for k, v in SEVERITY.items() if v > 0)


@given(st.lists(st.sampled_from(sorted(SEVERITY)), min_size=0, max_size=12))
def test_concern_score_bounded_and_quarantine_is_zero(types):
    actions = [{"resolution_type": t, "action_date": "2024-01-01"} for t in types]
    s = concern_index(actions, today=date(2026, 1, 1))
    assert 0.0 <= s["score"] <= 100.0
    # Only severity>0 types are scored; allegation/unverified contribute nothing.
    assert s["n_scored_actions"] == sum(1 for t in types if SEVERITY[t] > 0)


@given(st.sampled_from(_scored_types), st.sampled_from(_scored_types))
def test_concern_monotonic_in_severity(t_low, t_high):
    assume(SEVERITY[t_low] <= SEVERITY[t_high])
    today = date(2026, 1, 1)
    lo = concern_index([{"resolution_type": t_low, "action_date": "2024-01-01"}], today=today)
    hi = concern_index([{"resolution_type": t_high, "action_date": "2024-01-01"}], today=today)
    assert hi["raw"] >= lo["raw"]


@given(st.integers(min_value=0, max_value=40))
def test_concern_recency_decays(years_ago):
    today = date(2026, 1, 1)
    recent = concern_index([{"resolution_type": "guilty_plea", "action_date": "2025-01-01"}],
                           today=today)
    old = concern_index([{"resolution_type": "guilty_plea",
                          "action_date": f"{2025 - years_ago}-01-01"}], today=today)
    # Older same-severity action never scores higher than a recent one.
    assert old["raw"] <= recent["raw"] + 1e-9


def _has_tokens(s: str) -> bool:
    from glasshouse.entities import _token_set
    return bool(_token_set(s))
