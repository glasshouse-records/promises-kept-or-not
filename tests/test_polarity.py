"""Polarity guard for the contradiction engine — voting AGAINST a proposal
is only a contradiction when the proposal ADVANCES the theme. Found 2026-06-15
in an interactive council review: ~half of one live batch were false positives
(anti-DEI proposals, anti-ESG counter-reports, case-by-case policies), one of
which would have been a backwards, defamatory accusation."""

from glasshouse.contradictions import commitment_is_discretionary, proposal_is_oppositional


def test_anti_theme_proposals_are_oppositional():
    # The Apple #1 case: voting AGAINST "cease DEI" DEFENDS diversity.
    assert proposal_is_oppositional("A shareholder proposal entitled 'Request to Cease DEI Efforts'")
    assert proposal_is_oppositional("Proposal to eliminate the company's net-zero commitments")
    assert proposal_is_oppositional("Report on climate risks to retirement plan beneficiaries")
    assert proposal_is_oppositional("Request for an alternative emissions report")
    assert proposal_is_oppositional("Adopt merit-based hiring and end DEI programs")


def test_pro_theme_proposals_are_not_oppositional():
    # Genuine pro-theme proposals — voting AGAINST these IS a contradiction.
    assert not proposal_is_oppositional("Report on lobbying alignment with the company's climate goals")
    assert not proposal_is_oppositional("Shareholder proposal requesting an anti-corruption report")
    assert not proposal_is_oppositional("Report on board diversity and inclusion metrics")
    # Oppositional VERB aimed at a HARM (not the theme's own program) is pro-theme.
    assert not proposal_is_oppositional("Proposal to end the use of forced labour in the supply chain")
    assert not proposal_is_oppositional("Report on efforts to eliminate deforestation")


def test_discretionary_policy_language_detected():
    assert commitment_is_discretionary(
        "A fund will vote case by case on all proposals requesting lobbying disclosure.")
    assert commitment_is_discretionary("We assess these on a case-by-case basis.")
    # "Factors we consider" lists are not commitments either.
    assert commitment_is_discretionary(
        "Factors for consideration include applicable laws regarding lobbying.")
    assert commitment_is_discretionary(
        "To assess a climate risk oversight failure, factors for the fund to consider include materiality.")
    assert not commitment_is_discretionary(
        "We are committed to robust climate risk oversight in our voting.")
    assert not commitment_is_discretionary(
        "We expect companies to disclose climate-related risks to investors.")
