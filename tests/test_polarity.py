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
    # CORRECTED 2026-07-06: "DEI goals in executive pay" was previously assumed
    # to mean "ADD DEI goals" (pro). Web-verified reality — the National Legal
    # and Policy Center's version asks to ELIMINATE DEI goals from executive
    # pay — makes the title polarity-ambiguous, so it is excluded, not counted.
    assert proposal_is_oppositional("Shareholder proposal on DEI goals in executive pay incentives")
    # A clearly pro-diversity proposal still counts.
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


def test_anti_dei_executive_pay_proposals_excluded():
    """Fatal live bug (2026-07-06): the 2024-25 anti-DEI campaign flooded
    ballots with "DEI goals in executive pay" proposals. The National Legal
    and Policy Center's version asks companies to ELIMINATE DEI goals from
    executive pay — voting AGAINST it is consistent with a diversity
    commitment, not a gap. The title alone can't distinguish 'eliminate DEI
    pay goals' (anti) from 'link pay to DEI' (pro), so these are excluded from
    gap-scoring. 445 such votes had leaked into the board-diversity rate."""
    for d in [
        "Shareholder Proposal Regarding DEI Goals in Executive Pay Incentives",
        "Shareholder proposal relating to DEI goals in executive pay incentives",
        "Vote on shareowner proposal regarding DEI goals in executive pay",
        "Advisory Vote to Revisit DEI in Executive Compensation.",
        "Shareholder Proposal: Regarding Report on Effectiveness of DEI Efforts",
    ]:
        assert proposal_is_oppositional(d), f"leaked anti/ambiguous DEI proposal: {d!r}"


def test_genuine_pro_diversity_proposals_still_count():
    """The fix must NOT gut real pro-diversity gaps: a plain civil-rights
    audit or a board-diversity report is pro-theme; voting it down is a real
    gap and must keep counting."""
    for d in ["Shareholder Proposal - Civil Rights Audit",
              "Shareholder proposal on a civil rights audit",
              "Report on board diversity and inclusion metrics",
              "Shareholder proposal requesting a report on board diversity"]:
        assert not proposal_is_oppositional(d), f"real pro-diversity gap dropped: {d!r}"


def test_commitment_to_vote_against_proposals_is_not_a_theme_commitment():
    """Live false positive (2026-07-06, second First Stone run): Goldman's
    'We generally will vote AGAINST proposals asking for detailed disclosure
    of political contributions or trade association or lobbying expenditures'
    was quoted as a lobbying-disclosure COMMITMENT. It is the opposite — an
    explicit commitment to oppose such proposals; voting against them is
    consistent. A SAY-side sentence whose object is voting down PROPOSALS is
    an anti-commitment, never a theme commitment."""
    from glasshouse.contradictions import commitment_is_oppositional
    assert commitment_is_oppositional(
        "We generally will vote AGAINST proposals asking for detailed disclosure "
        "of political contributions or trade association or lobbying expenditures.")
    assert commitment_is_oppositional(
        "We will not support shareholder resolutions seeking additional "
        "climate reporting.")
    assert commitment_is_oppositional(
        "The funds typically oppose proposals requesting lobbying reports.")
    # Voting against DIRECTORS for failing on the theme is a PRO-theme
    # commitment — the object matters:
    assert not commitment_is_oppositional(
        "We will vote against directors who fail to provide adequate climate "
        "risk oversight.")
    assert not commitment_is_oppositional(
        "We are committed to robust climate risk oversight in our voting.")


def test_may_support_is_discretionary():
    """Live false positive (same run): T. Rowe's 'To the extent that we find
    generally poor disclosure…, we may support shareholder resolutions asking
    for more transparency' — 'may support' reserves discretion."""
    assert commitment_is_discretionary(
        "To the extent that we find generally poor disclosure regarding the "
        "board's oversight of political activity, we may support shareholder "
        "resolutions asking for more transparency.")
    assert commitment_is_discretionary("The fund may vote for such proposals.")
    assert not commitment_is_discretionary(
        "We support shareholder resolutions asking for lobbying transparency.")


def test_deference_to_management_is_not_a_commitment():
    """Live false positive (first First Stone run, 2026-07-06): Goldman's
    policy sentence 'We generally believe that it is the role of boards and
    management to determine the appropriate level of disclosure of all types
    of corporate political activity' was quoted as a lobbying-disclosure
    COMMITMENT — but it is the opposite: an explicit deference to management.
    Voting against disclosure proposals is CONSISTENT with that sentence."""
    assert commitment_is_discretionary(
        "We generally believe that it is the role of boards and management to "
        "determine the appropriate level of disclosure of all types of "
        "corporate political activity.")
    assert commitment_is_discretionary(
        "It is the responsibility of management to determine what lobbying "
        "activity is disclosed.")
    assert commitment_is_discretionary(
        "These decisions remain the purview of the board.")
    # Deference language about OUR OWN duties must not trip the guard:
    assert not commitment_is_discretionary(
        "It is our role as stewards to press companies for climate disclosure.")
