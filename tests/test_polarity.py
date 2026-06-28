"""Polarity guard for the contradiction engine — voting AGAINST a proposal
is only a contradiction when the proposal ADVANCES the theme. Found 2026-06-15
in an interactive council review: ~half of one live batch were false positives
(anti-DEI proposals, anti-ESG counter-reports, case-by-case policies), one of
which would have been a backwards, defamatory accusation."""

from glasshouse.contradictions import (
    commitment_is_discretionary,
    is_binding_commitment,
    proposal_is_oppositional,
)


def test_binding_commitment_rejects_non_commitments():
    # Real manager commitments (first-person / fund agent, prose): accepted.
    assert is_binding_commitment("We are committed to supporting inclusive organisations.")
    assert is_binding_commitment("The fund will vote against directors for insufficient progress.")
    assert is_binding_commitment("We expect companies to report material climate risks.")
    # TOC / title-case list fragment from a PDF — NOT a commitment.
    assert not is_binding_commitment(
        "Americas EMEA Asia-Pacific Impact Net Zero Executive Compensation Environmental Social Political")
    # Describes an issue / states an expectation OF companies, manager binds nothing.
    assert not is_binding_commitment("The board should reflect the diversity of the workforce.")
    assert not is_binding_commitment(
        "This is particularly relevant to a company's workforce, central to long-term value.")
    # Too short to be a quotable commitment.
    assert not is_binding_commitment("We vote proxies.")


def test_anti_dei_revisit_genre_is_oppositional():
    # The anti-ESG "revisit/revising DEI" genre — voting AGAINST DEFENDS diversity,
    # so it must NOT count as diversity-hypocrisy (found in audit 2026-06-28).
    assert proposal_is_oppositional("Report on Delays in Revising Diversity, Equity, and Inclusion (DEI) Initiatives")
    assert proposal_is_oppositional("Advisory Vote to Revisit DEI in Executive Compensation")
    assert proposal_is_oppositional("Proposal to reevaluate the company's diversity programs")
    # The "risks OF DEI" anti-ESG genre — DEI framed as the risk (anti).
    assert proposal_is_oppositional("Report on the Risks of the Company's DEI Program")
    assert proposal_is_oppositional("Report on DEI and Related Risks")
    assert proposal_is_oppositional("Shareholder proposal requesting report on the risks of maintaining DEI efforts")
    # …but a proposal to ADD diversity goals is pro-theme (must still count).
    assert not proposal_is_oppositional("Shareholder proposal on DEI goals in executive pay incentives")
    assert not proposal_is_oppositional("Report on board diversity")
    # …and environmental risk-disclosure stays pro (the harm is the risk, not the program).
    assert not proposal_is_oppositional("Report on Risks Related to Biodiversity and Nature Loss")
    assert not proposal_is_oppositional("Report on financial risks related to climate change")


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
