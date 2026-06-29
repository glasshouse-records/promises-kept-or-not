from glasshouse.entities import fuzzy_match, normalize_name


def test_normalize_strips_legal_suffixes():
    assert normalize_name("Goldman Sachs Group Inc.") == "goldman sachs"
    assert normalize_name("BP p.l.c.") == "bp"
    assert normalize_name("3M Co") == "3m"


def test_normalize_keeps_descriptive_words_to_avoid_collisions():
    # Descriptive words are part of the name — stripping them collapsed DISTINCT
    # companies and caused false joins (audit 2026-06-28). They must be kept.
    assert normalize_name("Pineapple Energy Inc.") == "pineapple energy"   # not "pineapple"
    assert normalize_name("Acme Technologies Inc.") == "acme technologies"
    assert normalize_name("Acme Solutions LLC") == "acme solutions"
    # …so distinct companies don't normalize to the same key:
    assert normalize_name("Acme Energy Inc.") != normalize_name("Acme Inc.")


def test_exact_normalized_match():
    matched, score = fuzzy_match("Goldman Sachs Group Inc.", "goldman sachs")
    assert matched and score == 1.0


def test_false_positive_classes_rejected():
    # The classic substring-match failure modes must stay dead.
    assert fuzzy_match("Apple Hospitality REIT Inc", "Apple Inc")[0] is False
    assert fuzzy_match("BAE Systems", "AES Corp")[0] is False
    assert fuzzy_match("General Electric", "GE Healthcare")[0] is False


def test_token_subsequence_with_length_guard():
    matched, score = fuzzy_match("Smith & Wesson Brands", "smith & wesson")
    assert matched and score >= 0.85
    # length-ratio guard: "bp" must not match a long unrelated name
    assert fuzzy_match("bp", "british petroleum exploration ltd")[0] is False


def test_cusips_never_fuzzy_match_names():
    matched, _ = fuzzy_match("68389X105", "Oracle Corp")
    assert matched is False
    matched, _ = fuzzy_match("68389X105", "68389X105")
    assert matched is True
