# Glasshouse Methodology

**Version:** 0.1 (DRAFT — prerequisite for any public claim; no finding may be
published while this document is marked DRAFT)
**Last updated:** 2026-06-11

---

## Purpose

Glasshouse joins three classes of public primary-source records:

1. **SAY** — institutions' own published commitments (stewardship and proxy
   voting policies, ESG reports, signatory statuses), snapshotted and
   versioned.
2. **DO** — institutions' observable choices: proxy votes (SEC Form N-PX),
   holdings (13-F, N-PORT).
3. **DONE** — the documented enforcement record of companies they hold and
   vote on — and of the institutions themselves.

Its output is findings of the form *commitment X (archived DATE) vs. act Y
(primary ref. Z)*, each fully traceable.

## Evidence ledger invariants

Every record in the ledger carries:

- `source_url` — the public primary source it was retrieved from
- `retrieval_date` — when it was retrieved
- `primary_ref` — the agency's own reference number (DOJ press release no.,
  SEC litigation release no., OFAC entity number, NLRB case no.) where one
  exists; records without one are flagged by the integrity checker
- `resolution_type` — the legal character of the action (see below)

Records originating from curated snapshots (hand-verified research imported
from a predecessor project) are marked `source_kind = curated_snapshot` with
the snapshot's extraction date, and are scheduled for re-verification against
live sources before being used in any published claim.

## Resolution types — the legal distinction table

This table is reproduced in every output that references an enforcement
action. The differences are legally material and are never collapsed.

| Resolution type | Criminal conviction? | Admission of guilt? |
|---|---|---|
| **Guilty plea** | Yes | Yes |
| **DPA** (Deferred Prosecution Agreement) | No — charges dismissed if compliant | No |
| **NPA** (Non-Prosecution Agreement) | No — no charges filed | No |
| **Civil settlement** (e.g. SEC) | No (civil only) | Typically no |
| **Civil violation / board order** (NLRB, EPA, etc.) | No (administrative/civil) | N/A |
| **Debarment** (World Bank) | No (administrative) | N/A |
| **Sanction designation** (OFAC) | No (administrative) | N/A |
| **Expulsion** (UN Global Compact) | No (membership action) | N/A |
| **Docket / pending matter** | **Allegation only — never reported as a finding** | — |

Records whose resolution type cannot be determined from the primary source
are stored as `unverified` and quarantined: they cannot appear in any
published output until a human verifies the primary source (see
[PENDING_VERIFICATION.md](PENDING_VERIFICATION.md)).

## Finding classes (strongest first)

1. **Commitment ⟷ vote** — the flagship. A vote is an active choice; the
   "passive index" defense does not apply.
2. **Vote divergence within one manager** — the same manager's fund families
   voting opposite ways on an identical proposal (e.g. ESG-branded funds vs.
   flagship index funds). Validated as a real, recurring pattern (2026-06-10).
3. **Commitment ⟷ the institution's own enforcement record.**
4. **Commitment ⟷ silent policy edits** between snapshots.
5. **Commitment ⟷ holding** — weakest (index alibi exists); still reported,
   labeled as such.

## The evidence engine (proposal-level; supersedes line-level rates)

`engine.py` builds a derived index (`data/engine.db`, rebuildable, never a
source of truth) that every investigation now goes through. It differs from
the say-vs-do analysis described below in three ways, each a correction:

- **The unit is the proposal, not the ballot line.** N-PX reports one line per
  fund per ballot item. As of 2026-11-16 (three N-PX seasons, 2024–2026) the ledger's 280,687
  shareholder-proposal lines are 56,164 distinct (manager, company, meeting, proposal) decisions. Rates over
  lines weight a proposal by how many of a manager's funds hold the stock;
  the engine counts each decision once. The position is SHARE-weighted:
  funds routinely file a sliver the other way (0.2–2.5% of shares at State
  Street), so the minority side must carry at least 5% of shares voted before
  the position is `SPLIT`. Counting lines instead called 801 State Street and
  604 BlackRock proposals split and dropped them from every rate; share
  weighting leaves 7 and 3. `SPLIT` is outside the support rate
  (FOR / (FOR + AGAINST)) and reported beside it.
- **Coverage is a handful of fund registrants per manager** (BlackRock,
  State Street and T. Rowe Price: four each; Vanguard: five; index trusts
  only for the largest three, added 2026-11-16). Figures describe "the funds on file", not the firm.
- **Scope is shareholder-sponsored proposals** (`vote_source = SECURITY
  HOLDER`), de-duplicated, plus **management's director nominees**
  (`vote_source = ISSUER`, category `DIRECTOR ELECTIONS`) in a separate table
  with their own tools. Director items are counted per nominee item as filed
  and per meeting; `opposed` is AGAINST or WITHHOLD, share-weighted. N-PX
  never records the reason for a vote, so a director-opposition rate cannot
  be attributed to any one policy provision (diversity, overboarding, pay).
  Managers are compared on shared MEETINGS (CUSIP + date), not on matched
  nominees: filers word nominee items differently. Other management
  proposals stay in the ledger but are not indexed.
  Each director item carries `isin_country`, the first two letters of the
  ISIN on its fund lines. That is the country that *issued the ISIN*, not
  where the company is run (a Cayman-registered company is `KY`); it is NULL
  where no line has an ISIN, the prefix is malformed, or the lines disagree.
  The director tools accept `country=` (`US`, `US,CA` or `non-US`); items with
  no usable country are excluded then, and the number excluded is stated in
  the result's caveats. `director_record` splits US / non-US / unknown.
  **Withhold vs abstain is the filer's coding, not ours.** In a US plurality
  election a withheld vote can be filed as WITHHOLD (counted in `opposed`) or
  as ABSTAIN, and N-PX does not define the choice; a change of filing agent
  changed it (BlackRock BIS, US ISINs, calendar years: `opposed` 1,216 in 2024
  against 617 in 2025 while `abstain` went from 166 to 570). The director tools
  therefore also report `not_supported` = `opposed` + `abstain` and
  `non_support_rate` = `not_supported` / (`for` + `opposed` + `abstain`); SPLIT
  and NONE items are in neither, as for `opposed`. A result that lists several
  periods of one group carries a `CODING SHIFT` caveat, with the abstain counts,
  whenever the abstain share of `not_supported` differs by more than 15 points
  between two of them (and one holds at least 30 abstain items): `opposed` is
  then not comparable across the periods. For comparisons over time use
  non-support. The desk verifier refuses a draft paragraph that cites `opposed`
  or `opposition_rate` from such a result without the matching `not_supported`
  or `non_support_rate` claim. `peers` and `director_peers` accept
  `institution=` (and `adviser=`) to show one group's row without changing any figure.
  **Say-on-pay is a third indexed category.** `pay_record` covers management items filed under N-PX category SECTION 14A SAY-ON-PAY VOTES (one row per manager and adviser per ballot item, same grouping, `is_duplicate = 0`, `adviser=`, `country=` and `CODING SHIFT` rules as director votes); say-on-pay *frequency* items (1/2/3 years) are not for/against, so they are excluded from every count and reported only as `frequency_items`.
- **Peer comparison is on identical proposals.** `peers` matches the same
  ballot item across managers by company, meeting date and the proposal's
  significant words. Matching is deliberately strict: an unmatched proposal
  costs a comparison; a false merge would compare votes on different items.
- **Say is time-aligned to do.** A vote is set only against the policy
  version archived on or before the meeting date. Capture dates are "public
  by", so the true window opens earlier and votes just before a capture are
  attributed to the previous version.

Figures produced by the older line-level modules (`investigate`, `systemic`,
`detectors`, `casefile`) are NOT comparable to engine figures and should not
be cited alongside them. The 175 rows in `findings` predate the temporal
guard — 25 of them pair a vote with a policy version archived after it — and
all remain `pending`; none is publishable.

**Drafts are machine-checked.** An investigating agent files a draft to
`data/desk/` in which every factual sentence carries a claim (`quote`,
`absent`, `stat`, `proposal`, `enforcement`). `glasshouse desk verify`
re-executes each claim against the engine, rejects uncited figures and
unbacked quotations, and rejects words asserting motive or wrongdoing. A
verified draft is an unpublished lead; publication remains a human act.

**Which adviser votes.** One institution can hold fund registrants whose
shares are voted by different advisers under different published policies
(T. Rowe Price: TRPA and TRPIM, which run controls against sharing proxy
decisions). `config/institutions.yaml` names the voting adviser per registrant
(`adviser_key`, with the prospectus cited in `adviser_source`) and the adviser
that owns each policy document. Only an explicit `adviser_key` separates
advisers; a free-text `adviser` label alone does not. For an institution with
two or more known advisers the engine never aggregates lines voted by different
advisers into one item: each adviser's decision is its own row, peers tools
list each as `institution/ADVISER`, every vote tool takes `adviser=` (an
unknown adviser is refused), and an unscoped answer carries a POOLED ADVISERS
caveat. Tools that pair policy text with votes (`say_vs_do`) refuse without
`adviser=` and use only that adviser's documents; `policy_in_force` needs the
adviser or document. The draft verifier rejects a vote claim about such an
institution that does not carry the adviser. Registrants with no `adviser_key`
are "unknown", not assumed to share anyone's policy.

The group is resolved per vote line, not per registrant: a registrant's
`adviser_key` is its default; `adviser_key_history` (inclusive `from`/`until`
ISO dates, compared with the MEETING date) and `series_adviser` (per fund
series, optionally dated) override it, in that order (series rule, then
history, then default). A meeting date that does not parse, on a series or
registrant that has any dated rule, resolves to `UNDATED`: its own group, never
paired with a policy (the adviser in force cannot be told). Rule bounds are
validated at build (ISO days, `from` <= `until`, no overlaps) and a bad rule
stops the build. A policy document takes its key the same way, from its own
`adviser_key_history`, on each version's CAPTURE date (the day the text was
demonstrably public), not its authored date: a policy is often written days
before it takes effect (Vanguard's VPM text was authored 2026-01-06, effective
2026-01-12). Tools say when a version was authored over 30 days before its
first capture, and how many votes precede an adviser's first archived text.
Vote lines with no key on record are a group of their own (`unlabelled`)
whenever the institution has any keyed registrant or document. An institution
is multi-group when its lines resolve to
two or more keys, its documents carry two or more keys, or a document's key is
none of the registrants' keys (a policy that does not govern the votes on
file: Deutsche's DWS Investment GmbH letter versus US trusts voted by DIMA).
Pairing tools use only documents keyed to the adviser asked for and refuse,
rather than fall back to another group's text, when that adviser has none.
The key `EXTERNAL` marks series advised by an outside manager: a group like
any other, never paired with any policy document. An institution's
`voting_scope_notes` are appended verbatim as caveats to its vote and policy
tool results.

### SAI-printed policy versions (added 2026-11-18)

Where a sub-adviser's own website has no archive history (Geode, Wellington),
the funds it votes for reproduce its proxy policy in an appendix of their
Statement of Additional Information (EDGAR forms 485BPOS). For these managers
Glasshouse extracts that one section from each SAI, between two configured
heading texts, and records it as a policy version under a SEPARATE document
label (`...-as-printed-in-sai`; the source is shown as `edgar-sai`), never
under the website PDF's label, because the printed formatting differs and a
shared label would invent alternating versions. The date of such a version is
the EDGAR filing date of the earliest filing carrying that text, and it means
only that the text was public by that day: it is not the date the manager wrote
or adopted it. Version identity is the extracted section text, ignoring all
whitespace and (for Wellington) printed page numbers; identical text in later
filings is the same version. If a start heading is not found cleanly, or the end
heading does not follow it, that filing yields nothing (a multi-SAI filing that
prints the section several times is accepted only when every copy is identical).

A website HTML page whose navigation or trademark spacing changes between captures would mint phantom versions if the whole page were the text. A commitment label may therefore carry `body: {start, end}` (config/institutions.yaml): the policy text is the span from the first `start` match to the first `end` match after it, whitespace-normalised, and version identity, sentences and quote checks use only that span. A capture where either marker does not match is unreadable (never a new version, never the full page) and is logged. Currently used for American Century's website page. For every label, identity text also has whitespace removed before a trademark sign (®, ™, ©), because that spacing never changes meaning. Identity text also maps typographic quotes (‘ ’ “ ”) to ASCII, writes every dash (em, en, or a spaced hyphen) as one form, and removes a space between a number and "%" ("15 %" = "15%"): none of that changes meaning. The normaliser is versioned (`commitments.identity_version`); when it changes, the backfill recomputes every stored identity from the local file (rows with no file keep their stored hash and are logged).

**Declared reprints.** An SAI appendix is re-printed in each annual update, sometimes with page-break or typesetting differences only. A human who has diffed an edition against its predecessor and found no wording change may declare it in config under that label: `sai_appendix.reprints: [{accession, same_as_previous: true, reason, checked}]`. The reprint's capture is kept (row and file, never deleted, id never reused) and is marked `commitments.reprint_of` = the id of the edition it reprints; it takes that edition's `identity_sha256`, so it is not a new version, and the earlier edition stays dated by its own earliest filing (`public_by`). Removing the declaration restores the capture's own identity at the next backfill. A reprint is never declared if any word of policy changed; the reason is written in the config and the check date recorded. One shared helper (`contradictions.commitment_identity`) computes identity for the engine, release, site, dataset, newsroom and timeline; the release's `policy_versions.text_sha256` is the hash of exactly that text. The ledger's own `text_sha256` is unchanged (whole page, whitespace only).
Filings that cannot be extracted are therefore missing versions, not guesses;
a policy edit between two extracted filings is dated to the later one's
filing, so the version in force may have been public earlier than shown.

Parametric Portfolio Associates (added 2026-11-18): parametricportfolio.com
answers requests that identify themselves honestly with 403 (probed
2026-11-18; the same pages open for other client strings). Glasshouse does not
change its identification to get in, so no website copy of Parametric's policy is
archived. The only dated text is the SAI route: the Parametric Tax-Managed
Emerging Markets Fund SAI printed Parametric's own policy as an appendix in
the 2023, 2024 and 2025 editions (label `parametric-proxy-voting-policy-as-printed-in-sai`;
printed page footers stay in the text). The 2026 SAIs print Morgan Stanley
Investment Management's Equity Proxy Voting Policy instead, which names
Parametric as a covered affiliate but is a different document and is not
filed under Parametric's key; the copy those SAIs print is archived on its own
as `msim-equity-proxy-voting-policy-parametric-as-printed-in-sai`, keyed
PARAMETRIC_MSIM (the key the votes carry from that SAI's date), never under
Parametric's own key or the MSIM key. Re-check the website if a sanctioned path appears.

Morgan Stanley Investment Management (added 2026-11-18): morganstanley.com/im
and eatonvance.com answer requests that identify themselves honestly with 403
(`proxyvotingpolicy_msim_en.pdf`, probed 2026-11-18; a third host timed out).
Glasshouse does not change its identification to get in, and a 403 is a block,
not proof the file is gone, so no website copy of the MSIM Equity Proxy Voting
Policy is archived. The sanctioned path used is the SAI route: the Morgan
Stanley Institutional Fund, Inc. SAI prints the policy as Appendix A (label
`msim-equity-proxy-voting-policy-as-printed-in-sai`; the heading changed
between editions, so several start headings are listed; printed page footers
such as "A-9 Back to Table of Contents" are removed; a filing that prints the
heading twice yields nothing). Re-check the website if a sanctioned path appears.

Nuveen / TIAA (added 2026-11-18): nuveen.com and documents.nuveen.com answer
requests that identify themselves honestly with "Your request was blocked"
(probed earlier; Glasshouse does not change its identification to get in), so
no website copy of the Nuveen Proxy Voting Policy is archived. The sanctioned
path used is the SAI route: the Nuveen Investment Trust SAI prints the Nuveen
Proxy Voting Policy, Guidelines and Conflicts of Interest Policy as an appendix
(label `nuveen-proxy-voting-policy-as-printed-in-sai`; the filing prints it
twice, once per SAI, and both copies must be identical; printed page numbers
are removed). Re-check the website if a sanctioned path appears.

MFS (added 2026-11-18): mfs.com answers requests that identify themselves
honestly (200 on the home page and on the policy page; probed 2026-11-18), so it
is not a blocked source. The policy page itself links no PDF in its markup; the
direct copy found is `.../content/dam/mfs-enterprise/microsites/meridian/proxy_voting_procedures.pdf`
(200, application/pdf, dated January 1, 2026), archived as
`proxy-voting-policies-and-procedures`. Other mfs.com paths seen in search
results (`.../mfscom/news/proxy_voting_procedures.pdf`, the older US insights
page) answer 404 and are not relied on. The dated SAI route is archived under a
separate label, `mfs-proxy-voting-policies-as-printed-in-sai`: each December
485BPOS of MFS Series Trust I restates Appendix E for the coming 1 January in a
supplement and also prints the edition then in force in the SAI itself, so a
filing holds two different editions. Only the restated supplement is read (the
heading must be preceded by "restated in its entirety as follows"), which dates
each edition to the December filing that announced it; the supplement code and
page numbers ("MULTI-SAI-SUP-I-122925 8") are removed because they carry the
SAI's own date. The edition of 1 January 2022 and earlier is not archived. The
municipal trusts and the money-market trust file N-PX with no equity votes and
are not ingested.

American Century (added 2026-11-18): americancentury.com answers requests that
identify themselves honestly (200 on `.../about/proxy-voting-policies/`, probed
2026-11-18; the home page is slow and one guessed path returned repeated 500s,
so only the policy page is requested), so it is not a blocked source. The policy
is the HTML page body (no PDF is linked); it prints "Last Revised: June 2025",
and the page text includes site navigation, so a navigation change can add a
version that is not a policy edit (the first three Wayback captures, 2022-06-25 to 2023-02-07, carry one identical policy body and differ only in navigation). It is archived as `proxy-voting-policies`.
The dated route is `american-century-proxy-voting-policies-as-printed-in-sai`:
Appendix E of the American Century Mutual Funds SAI (one copy per 485BPOS, read
from the appendix heading to the SAI back cover; the table-of-contents line is
not the heading; page numbers "E-n" are removed). It yields four editions
(2022-02-28, 2023-10-23, 2024-02-28, 2026-02-27, the 2022 text says "Advisor",
later ones "Adviser"). American Century Investment Management votes every
series, sub-advised series included (Nomura Corporate Research and Asset
Management is a named investment sub-adviser only); the Avantis funds and ETFs
are its products under the same policy. The Asset Allocation, Government
Income, Municipal, California Tax-Free, International Bond and Target
Maturities trusts, Variable Portfolios II, and the institutional-manager filers
are not ingested (no operating-company votes in a fund registrant's N-PX, or not
a fund).

Janus Henderson (added 2026-11-18): janushenderson.com answers requests that
identify themselves honestly (200 on `.../investor/legal-information/proxy-voting/`,
probed 2026-11-18), so it is not a blocked source. The policy page is navigation
plus a link; the policy itself is a PDF reached through
`/download/document/131419` (301, 302, 200 `application/pdf`), whose CDN file name
changes with each edition ("Proxy Voting Policy July 2026"). It is archived as
`proxy-voting-policy`; because the page is not the policy text no `body` bound is
needed, and the earlier CDN file names found in the Wayback CDX index are walked
under the same label as `former_urls` (editions "Last Review Date" March 2021,
March 2022 and February 2025 from Wayback captures 2021-06-15, 2022-06-19 and
2025-08-27, plus July 2026 live; the Wayback CDX endpoint throttled during a
pipeline-wide `--wayback` run on 2026-11-18, so a later run may add captures).
The dated route is `janus-henderson-proxy-voting-policy-as-printed-in-sai`:
Appendix B of the Janus Investment Fund SAI (read from the policy title to the SAI
back cover; one copy per SAI, accepted only when every copy in a filing is
identical). It yields five editions printing "Last Review Date" March 2023
(2023-10-27), February 2024 (2024-06-20), February 2025 (2025-06-24), September
2025 (2026-03-04) and July 2026 (2026-10-28). The contents list, bullets, the
footnote naming who votes for the Proprietary U.S. Funds, and page numbers are
removed because they follow each SAI's pagination; before the October 2023 edition
the SAI printed only a "Proxy Voting Summary", which is a summary and is not
archived. Voting: each trust's SAI says its Trustees delegated proxy voting to the
Adviser, Janus Henderson Investors US LLC. Intech Investment Management voted
its own sub-advised series until its agreements ended (Janus Investment Fund's four
Intech Managed Volatility funds, terminated 2022-04-05; the Janus Aspen U.S. Low
Volatility Portfolio until 2023), so each registrant is keyed from the first SAI in
which the Adviser alone votes (2022-10-28, 2023-04-28, and 2022-02-28 for the
Detroit Street Trust ETFs). Kapstream and the other foreign affiliates work under
personnel-sharing arrangements and do not vote. Clayton Street Trust (a fund of
funds, only Vanguard and Franklin ETF ballots) and the institutional-manager
reports are not ingested.

AllianceBernstein (added 2026-11-18): alliancebernstein.com answers requests that
identify themselves honestly (200 on `/nz/en/institutions/proxy-and-governance.html`
and on the policy PDF, probed 2026-11-18; the guessed US and corporate page paths
return 404, the policy is not on a US HTML page), so it is not a blocked source. The
policy pages are navigation plus a link; the policy itself is
`/content/dam/corporate/corporate-pdfs/AB-Proxy-Voting-and-Governance-Policy.pdf`
(`application/pdf`, first page "October 2025"), requested directly, so no `body`
bound is needed. It is archived as `proxy-voting-and-governance-policy`: the live
copy plus 7 Wayback captures of the same URL (2021-05-14 to 2025-07-05), whose first
pages print the editions March 2021, August 2021, March 2022, March 2023, September
2023, August 2024 and May 2025 (each capture is a different edition and a real
rewrite: the diffs run from 85 to 449 changed passages). The dated route is
`alliancebernstein-proxy-voting-and-governance-policy-as-printed-in-sai`: Appendix A
of the AB Large Cap Growth Fund SAI (one copy per annual 485BPOS, read from the
"Proxy Voting and Governance Policy Statement" heading to Part C of the registration
statement; the page marks "A- n" and "Table of Contents" are removed). It yields
four editions (2022-10-28, 2023-10-27, 2025-10-28 and 2026-10-28; the last differs
from the one before by a single typo fix, "client's" to "clients'"). That fund's
SAI is used because its single October cycle prints each edition once: the AB Cap
Fund filings alternate between typographic renderings of one edition (straight
versus curly quotes, "DC" versus "D.C."), which would invent alternating versions.
Other AB registrants carried an edition before that SAI did (the 2023 rewrite in the
Cap Fund SAI of 2023-06-30, the 2025 rewrite in the Cap Fund SAI of 2025-07-28), so
these dates are upper bounds: the text was public by that day, not first on it.
Voting: each trust's SAI says the funds adopted the Adviser's (the Bernstein Fund:
the Manager's) proxy voting policies and procedures and prints the policy as an
appendix; the closed-end Global High Income Fund prints it in Item 7 of its N-CSR.
No SAI read names a sub-adviser that votes (the AB Multi-Manager Select sub-advisory
agreements listed as Cap Fund exhibits are 2017 exhibits), and the Bernstein Fund,
the former Sanford C. Bernstein Fund, prints the same policy, so there is one key,
ALLIANCEBERNSTEIN, and no EXTERNAL series. Each registrant is keyed from the
EDGAR filing date of the earliest SAI (N-CSR for the closed-end fund) read, between
2022-01-28 and 2023-02-14. The Corporate Shares, Fixed Income Shares, Municipal
Income Fund II, National Municipal Income Fund, Multi-Manager Alternative Fund and
Bernstein Fund II N-PX are notice reports with no vote table, and several older
AllianceBernstein funds last filed N-PX before the window; none is ingested.

Federated Hermes (added 2026-11-18): federatedhermes.com answers requests that
identify themselves honestly (200 on the home page, `/policies-and-disclosures` and
on PDFs under `/siteassets/documents/`, probed 2026-11-18; unknown page paths
redirect to the home page and unknown PDF paths return 404), so it is not a blocked
source. But the new site (an Optimizely CMS, a JavaScript shell) links no US adviser
proxy voting policy: its policy documents are the EOS and Hermes UK voting
guidelines. The US advisers' policy, "Proxy Voting Policies and Procedures: Voting
Client Securities" (form 50404), is a PDF served by Federated's own document server,
`services.federatedinvestors.com/teamsite-file-server/content/Federated+Advisors+-+Proxy+Voting+Policies`
with a signed `token` query string (the tokenless path answers 200 with an empty
body; the token the Wayback Machine captured is still accepted and returns the PDF,
`application/pdf`, created 2024-01-23). It is archived as
`federated-advisors-proxy-voting-policies`: the live copy plus one Wayback capture
(2020-12-02), whose PDF metadata date the editions April 2020 and January 2024 (a
2024-07-13 capture is byte-identical to the live copy); the text prints no edition
date, and the two editions differ in many passages (for example the UK/Ireland
CFO exception to the director rule). It is a PDF, so no `body` bound is needed. If Federated rotates
the token the live fetch fails and is logged, not rewritten around. The dated route is
`federated-hermes-proxy-voting-policies-as-printed-in-sai`: the Federated Hermes
Global Allocation Fund SAI (one copy per annual 485BPOS, read from "Proxy Voting
Policies As an investment adviser with a fiduciary duty" to "Proxy Voting Report A
report on", so the policy's last sentence, "...how the proposal shall be voted.", is
kept; page numbers 30-49, which print mid-text and shift by edition, are removed).
It yields five editions (2022-01-27, 2023-01-25, 2024-01-26, 2025-01-27, 2026-01-27;
the 2024 edition differs from the one before by two commas and one threshold, "at
least 15%" to "10%", of shareholders needed to call a special meeting). That fund is
used because a single-fund SAI prints one copy once a year; the multi-fund Federated
SAIs print differing copies (different advisers) and would invent versions, and other
trusts carried each edition earlier than this fund's SAI, so these dates are upper
bounds.
Voting: each trust's SAI says the Board has delegated to the Adviser (the Federated
advisory company it names, a Federated Hermes, Inc. subsidiary) authority to vote
proxies and prints the Federated policy. Series sub-advised by Hermes Investment
Management Limited (HIML) differ: their SAIs say the Adviser "has in turn delegated
to the Sub-Adviser, the authority to vote proxies", under HIML's own guidelines, and
the Federated summary excludes "Hermes Investment Management, which maintains its own
voting policy". Those series (Adviser Series Global Equity, U.S. SMID and SDG
Engagement Equity Funds; the Sustainable High Yield Bond Fund from its SAI of
2023-05-26) are keyed HERMES_HIML, dated from the SAI that says so; HIML's own policy
is not archived, so nothing is ever paired with that key. The International Equity
Fund names Polaris Capital Management as a portfolio sub-adviser only, the voting
delegation there is to the Adviser, so it is keyed FEDERATED_HERMES. Each trust is keyed
from the EDGAR filing date of the earliest SAI read (2022-01-26 to 2022-12-27; Adviser
Series per series). Money Market Obligations Trust and three municipal trusts (only
Nuveen and BlackRock fund ballots), the Core Trust (no SAI exists to say who votes) and
the notice-only registrants are not ingested.

Neuberger Berman (added 2026-11-18): www.nb.com answers requests that identify
themselves honestly with HTTP 429 and `x-vercel-mitigated: challenge` (a Vercel bot
challenge, probed 2026-11-18 on `/proxy-voting`, `/robots.txt` and the policy PDF;
a plain `curl` and the pipeline's own client get the same answer). Glasshouse does not
change its identification or solve the challenge, and a 429 is not a removal, so no
live copy of the policy can be captured today and the capture attempt is logged as
failed (the doctor reports it; the live label stays configured so the day the
challenge lifts, capture resumes). The sanctioned path is the Wayback Machine:
`/proxy-voting` redirected (301, seen in the 2024-07-12 capture) to the policy PDF
`nb.com/handlers/documents.ashx?id=e6b2f962-93ae-48b5-854e-627c89b3ea7f` (also served
as `...&name=S0301_nb_proxy_policy_procedures`), and Wayback holds captures of both
addresses from 2022-05-17 to 2026-05-11. They are archived as
`proxy-voting-policies-and-procedures`; the policy is a PDF, so no `body` bound is
needed. Editions by the date the PDF prints: January 2022, February 2023, March
2024, February 2025, and a re-issue of the February 2025 edition (capture 2026-05-11)
that spells "NB" out as "Neuberger" and renumbers the headings. The nameless address is
walked first because the walk keeps the first capture of each text it meets; the
2022-05-17 and 2025-04-13 captures carry the same text as the later `&name=` captures
of 2022-07-26 and 2025-11-02, so where an earlier capture was met second the
version is dated by the later one (an upper bound). The dated route is
`neuberger-berman-proxy-voting-policies-and-procedures-as-printed-in-sai`: Appendix B of the
Neuberger Berman Advisers Management Trust SAI (the trust whose April filing prints
one copy; the Equity Funds SAI prints the same editions in December and, in 2026,
twice), read from the edition heading to "PART C OTHER INFORMATION" so the last
sentence ("...break a tie vote.") is kept. Page marks "B- 3" and the running page
header "Proxy Voting Policies and Procedures", which falls at a different place in
each filing and minted phantom versions, are removed; the edition heading keeps
its title. It yields five versions: April 2019 (filed 2022-04-20; the SAI still
printed this 2019 edition in 2022 and 2023), the same edition with an updated
Proxy Committee roster (2023-04-14), March 2024 (2024-04-16), February 2025
(2025-04-15) and the "Neuberger" re-issue (2026-04-15). The SAI prints an edition up to
two years after the manager published it, so SAI dates are upper bounds.
Voting: each trust's SAI says "The Board has delegated to NBIA the responsibility to
vote proxies related to the securities held in the Funds' portfolios" (the
closed-end funds say it in Item 7 of the N-CSR) and prints the NB policy. Two series
are voted by an outside sub-adviser and are keyed EXTERNAL: the Absolute Return
Multi-Manager Fund of Alternative Funds (its SAI: NBIA "has delegated to each
Subadviser by contract the responsibility to vote proxies", under each Subadviser's
policy) and the Greater China Equity Fund of Equity Funds (sub-adviser Green Court,
whose own proxy voting policy the SAI prints; no N-PX in the window). Sub-advisers
that are NB affiliates (Neuberger Berman Europe Limited, Neuberger Berman Asia) vote
under the NBIA policy. Each registrant is keyed from the EDGAR filing date of the
earliest SAI (N-CSR for the closed-end funds) read, 2022-01-05 to 2022-12-15. The
municipal funds, NB Crossroads and NB Private Markets funds, the Neuberger Berman
trust companies and non-US advisers, NBIA (all notice reports) and Neuberger Berman
Group LLC (an institutional-manager report of separate-account votes, not fund votes)
are not ingested.

Allspring (added 2026-11-18; a separate institution from `wells_fargo`, which sold
its asset-management arm as Wells Fargo Asset Management in 2021 and keeps only its
13-F and enforcement record): allspringglobal.com answers requests that identify
themselves honestly (200, `text/html`, Cloudflare, probed 2026-11-18), so it is not a
blocked source. The policy page is HTML and its text includes navigation, a cookie
banner and a footer, so the label `proxy-voting-policies-and-procedures` carries a
`body: {start, end}` bound: from "Allspring Funds Proxy Voting Policies and Procedures
Scope of Policies and Procedures" (the Funds' preface, which names the eight
registrants, followed by the Allspring Global Investments Proxy Voting Policies and
Procedures and its footnotes) to the page footer ("LinkedIn", "CFA(R)" or "Quick
links", looked ahead to rather than consumed, so the last footnote is kept; the 2022
capture has no footer and ends at its own last sentence). Every capture matches the
start once. The page lived at `/legal/proxy-voting-policies-and-procedures.html` (Wayback
2022-05-26) and `/legal/proxy-voting-policies-and-procedures/` (2023-07-06) before
`/corporate/` (2024-04-14 on); the earlier addresses are `former_urls`. Seven versions
by identity, each a real wording change (consecutive bounded captures diffed): the
approval line prints November 2021 (capture 2022-05-26), March 2023 (2023-07-06),
28 February 2024 (2024-04-14), 13 June 2024 (2024-08-03), the same edition with the
client-administration e-mail address changed from "allspring-global.com" to
"allspringglobal.com" (2024-11-04), 14 February 2025 effective 1 March 2025
(2025-03-26; the policy was rewritten, 32,000 characters down to 22,000) and 10
February 2026 effective 1 April 2026 (2026-07-16, identical to the live page).  The Wayback captures from 2025-03-26 to 2026-03-16 carry one identical text.
The dated route is `allspring-proxy-voting-policies-and-procedures-as-printed-in-sai`:
the Allspring Variable Trust SAI (one 485BPOS a year, 2022-04-25 to 2026-04-23; the
Funds Trust files dozens of differently arranged SAIs a year, so the Variable Trust,
whose SAI prints the policy once and in one place, is the source), read from the policy
heading to "Policies and Procedures for Disclosure of Fund Portfolio Holdings I. Scope
of Policies and Procedures." so the last sentence is kept. Three headings cover the
printed wordings (2022-23 "Allspring Global Investments, LLC", 2024 "(Allspring)
Stewardship", 2025-26 "Introduction"); the running page marks "81 Back To Table of
Contents" and "Variable Trust Funds 83 Back to Table of Contents", which carry no
policy text, are removed. It yields five versions (2022-04-25, 2023-04-25,
2024-04-25, 2025-04-23, 2026-04-23); the SAI copy prints no approval date.
Voting: each SAI says "The Board of the Trusts has delegated the responsibility for
voting proxies relating to the Funds' portfolio securities to Allspring Funds
Management", which "utilizes the Allspring Global Investments Proxy Voting Policies and
Procedures, included below"; the policy's scope paragraph names Allspring Funds Trust,
Master Trust, Variable Trust and the four closed-end funds, and the website's Funds
preface also names the Exchange-Traded Funds Trust. Sub-advisers (Allspring Global
Investments LLC and UK, Galliard, and for the C&B Large Cap Value and C&B Mid Cap Value
funds Cooke & Bieler) may give input, but the policy reserves "the final voting decision"
to the Allspring Proxy Governance Committee, so no series is keyed EXTERNAL (a later SAI
that moved a series to a sub-adviser's own voting would need a dated carve-out). Each
registrant is keyed ALLSPRING from the EDGAR filing date of the earliest filing read:
Funds Trust, Master Trust and the four closed-end funds 2022-01-25 (U.S. Equity Funds SAI,
0001081400-22-000037), Variable Trust 2022-04-25 (0001081400-22-000339), Exchange-Traded
Funds Trust 2024-12-02 (0001081400-24-000733, its first filing with an SAI). The
closed-end funds' own N-CSRs only refer to the policy. Master/feeder: the master
portfolios of Allspring Master Trust carry the vote rows and their feeder funds in
Funds Trust (Large Cap Value, Small Company Growth, Small Company Value, Core Bond) carry
none, so a vote is counted once; of the 16,929 Master Trust vote lines of the 2025 N-PX,
110 coincide with a Funds Trust line on issuer, meeting, proposal and share count, in
different series (common holdings, not feeder echoes). The management company and
distributor, the 13-F filing holding companies (the 13-F filer is Allspring Global
Investments Holdings, LLC, CIK 1890906) and the Luxembourg funds file no fund N-PX and
are not ingested.

Lord Abbett (Lord, Abbett & Co. LLC; added 2026-11-18): lordabbett.com answers requests
that identify themselves honestly (200, probed 2026-11-18), so it is not a blocked source.
The policy page is a landing page that only links to the policy PDF, so no HTML page is a
label and no `body` bound is needed; the label `proxy-voting-policy-and-procedures` is the
PDF (`/content/dam/lordabbett-captivate/documents/Governance-and-Sustainability/Proxy-Voting-Policy-and-Procedures.pdf`,
`application/pdf`, first page "March 2026"). The PDF moved: `/content/dam/lordabbett/en/resources/proxyVoting/Proxy_Voting_Policy_and_Procedures.pdf`
(Wayback 2021-09-22 and 2022-05-17), `/content/dam/lordabbett/en/documents/sustainability/`
(page capture 2024-08-14) and `/captivate/documents/Impact/` (2024-12-02) are `former_urls`; only the
first is in the Wayback index. Versions on file: the March 2021 edition (Wayback 2022-05-17; the
2021-09-22 capture is a 5.4 MB PDF that Wayback serves cut at 1 MiB, so the walk now skips a
PDF with no end marker, but that one stub was recorded as id 249 before the guard existed and
is unreadable), the March 2026 edition as captured 2026-06-07 (with an "APPLIES TO" block and a
proprietary-use notice on every page) and the live PDF (PDF created 2026-08-21, same "March
2026" date but without those two elements: a re-issue under the same date, captured live).
The dated route is `lord-abbett-proxy-voting-policy-as-printed-in-sai`: Appendix C of the Lord
Abbett Affiliated Fund SAI (one 485BPOS a year, February, 2021-02-23 to 2026-02-25; a single
copy per filing, where the multi-series trusts file several differently arranged SAIs a year and
print a slightly different page layout), read from the appendix heading to "APPENDIX D
DESCRIPTION OF CORPORATE BOND RATINGS" so the last sentence is kept. Six headings cover the
printed editions (2020 "Proxy Voting Policies and Procedures", March 2021, "Sustainable Investing &
Proxy Voting Policy" November 2022, February 2024, February 2025, March 2026); the running page
marks "N Part II C- N" and "Part II C- N" are removed (the page number only when it equals the
mark). It yields six versions (2021-02-23, 2022-02-23, 2023-02-28, 2024-02-23, 2025-02-25,
2026-02-25), each a different printed edition. Voting: every SAI says "The Funds have delegated
proxy voting responsibilities to the Funds' investment adviser, Lord Abbett, subject to the
[Proxy / ESG and Proxy / Sustainability and Proxy / Board's] general oversight", with the policy
attached as Appendix C, so each of the ten registrants is keyed LORD_ABBETT from the EDGAR filing
date of the earliest SAI read (Affiliated Fund and Securities Trust 2021-02-23, 0000930413-21-000386
and -000387; Research Fund 2021-03-25, -000637; Investment Trust 2021-03-26, -000648; Series Fund
2021-04-08, -000740; Bond-Debenture, Mid Cap Stock and Global Fund 2021-04-26, -000876, -000875,
-000877; Trust I 2021-06-21, -001202; Developing Growth 2021-11-22, -001898). No SAI names an
outside sub-adviser that votes a series' proxies, so no series is EXTERNAL. Ingested N-PX 2024-26
(24,042 / 23,050 / 22,834 votes with is_duplicate = 0 for the seasons filed in 2024, 2025 and
2026; the Global Fund's 2026 report is a notice). Not ingested: Lord, Abbett & Co. LLC's own
institutional-manager N-PX (CIK 728100, say-on-pay votes only; 351 of its 520 cusip-and-meeting
lines in 2025 coincide with fund-registrant lines, so it would double count), and the seven
registrants that file notice reports only (Municipal Income Fund, the money-market fund, Credit
Opportunities, Floating Rate High Income, Corporate Opportunities, Flexible Income, Municipal
Opportunities).

Franklin Templeton and Putnam (Putnam Investments added 2026-11-19 under `franklin_templeton`;
Franklin Resources acquired Putnam on 2024-01-01): franklintempleton.com answers requests that
identify themselves honestly (200, probed 2026-11-19), so it is not a blocked source; the Putnam
policy page is an application shell that holds no policy text, so no HTML page is a label and no
`body` bound is needed. The institution now has two adviser groups. FRANKLIN: Franklin Custodian
Funds (CIK 38721, from 2021-01-26, SAI 0001379491-21-000215) and Franklin ETF Trust (CIK 1551895,
from 2021-07-28, SAI 0001379491-21-003455), whose SAIs say the board delegated voting to the
investment manager, Franklin Advisers, Inc.; policy label `proxy-voting-policies-procedures`
(Franklin Equity Group). PUTNAM: 13 fund registrants (Putnam Funds Trust, High Yield Fund,
Variable Trust, Investment Funds, International Equity Fund, George Putnam Balanced Fund, Global
Health Care Fund, Asset Allocation Funds, Diversified Income Trust, Convertible Securities Fund,
Large Cap Value Fund, Focused International Equity Fund, ETF Trust), each keyed PUTNAM from the
EDGAR filing date of its own earliest SAI whose Part II says "The Trustees of the Putnam Funds
have delegated proxy voting authority for the securities held in the funds' portfolios to Putnam
Management and have approved Putnam Management's current proxy voting guidelines and procedures"
(2023-03-27 to 2024-02-26; the ETF Trust's SAI said so from 2021-05-20; accessions in each
registrant's `adviser_source`). SAIs up to 2023-02-28 say the opposite: the Trustees established
the guidelines and a Director of Proxy Voting and Corporate Governance in the Office of the
Trustees directed the votes. That is not Putnam Management voting, so earlier meetings stay
unlabelled, and so do meetings between 2023-07-01 and a registrant's first SAI of the new wording
(Large Cap Value, Convertible Securities and Focused International Equity: until 2024-02-26),
although the SAI footnote says the Board delegated "effective January 27, 2023"; a sister trust's
filing is never used to date another registrant. No rule ends: the SAIs read to 2026-10-26 still
say Putnam Management votes under the Putnam Investments Proxy Voting Procedures, also where
Franklin Advisers, Inc. became the Investment Manager of a series in 2025-26 and Putnam
Management sub-advises it. No series is EXTERNAL: PanAgora Asset Management (sub-adviser of the
Putnam PanAgora ESG ETFs) is described as making investment decisions only. Not ingested:
Putnam's institutional-manager N-PX reports (CIKs 81273, 81238, 1140334: they overlap the fund
tables), the notice-only funds (Money Market, Income, Global Income, California Tax Exempt) and
High Income Securities Fund (Putnam in name until 2018). Ingested N-PX 2024-26: 96,135, 94,465
and 101,865 votes with is_duplicate = 0 for the seasons filed in 2024, 2025 and 2026. Policy: label
`putnam-investments-proxy-voting-procedures` is the franklintempleton.com PDF
(`/forms-literature/download/PI-PVG`, first page "March 28, 2025"; commitments id 251) with the
earlier putnam.com address `/static/pdf/proxy/proxy_voting_procedures_guidelines.pdf` walked as a
`former_url` (March 26, 2021 edition, Wayback 2021-10-28, id 257); putnam.com's
`/static/pdf/proxy/proxy_voting_guidelines.pdf` is deliberately not walked: its 2014-2021 captures
are the Putnam Funds' own Trustee guidelines (another document) and it still serves the July 1,
2024 edition live. The dated route is `putnam-investments-proxy-voting-procedures-as-printed-in-sai`:
Appendix A of the Putnam Variable Trust SAI (one 485BPOS a year plus one in October 2026; the
multi-series Putnam trusts file many differently typeset SAIs a year, whose bullet glyphs and
split words would mint a version each), read from "Putnam Investments Proxy Voting Procedures
Introduction and Summary" to the Part C heading, so the final certification sentence is kept. The
SAI's own page numbers (a bare number at every page foot from 2025, mid-sentence too, "Month D,
YYYY II- n" before) are removed by the opt-in `page_sequence` (the longest run of at least eight
consecutive numbers, never a lone number), bullet glyphs and signature blanks by `strip_patterns`.
Five versions (2023-04-28 January 2023 edition, 2024-04-29 March 2024, 2025-04-28 March 2025,
2026-04-20, 2026-10-01), diffed consecutively: the first three and the last differ in wording; the
2026-04-20 version is the 2025-04-28 text with one list item moved across a page break and one
split word ("A n"), a layout difference the extraction cannot remove (known phantom, commitments
id 255).

Principal (Principal Global Investors, LLC, doing business as Principal Asset Management; added
2026-11-19): `brandassets.principal.com` answers requests that identify themselves honestly (200,
`application/pdf`, probed 2026-11-19), so it is not a blocked source. principalam.com has no link to the
policy (its page says a client may ask for it); the PDF `/m/7a1042bf82d83012/original/Policy-on-Proxy-Voting-for-Investment-Advisory-Clients.pdf`
(first page "February 2026", PDF created 2026-03-04) is the label `proxy-voting-policies-and-procedures`.
The same host also serves a different document (the Principal Global Investors Trust Company Proxy
Voting Policy, December 2025) that is not this label. Wayback holds six captures of the address
(2025-02-06 to 2026-04-08); nothing older was found (a prefix CDX query returned HTTP 500, backed
off, not retried in a loop). The dated route is `principal-proxy-voting-policy-as-printed-in-sai`: the PGI
policy printed in the Principal Exchange-Traded Funds SAI (CIK 1572661, 485BPOS), read from the
policy heading to the start of the Spectrum Asset Management policy that follows it; six headings
cover the printed editions ("Proxy Voting and Class Action Monitoring" 2021, the 2021-10 and 2022
re-titlings that name Principal Real Estate Investors, "Proxy Voting Policies and Procedures",
"Proxy Voting Policy" 2025, "Principal Asset Management SM ... February 2026"), and the running
footer "Principal Global Investors PGI Global Compliance Manual" is removed. An SAI with no Spectrum
policy after the PGI one (the 2026-04-20 filing) contributes nothing. Voting: every SAI of the three
registrants says the Board delegated proxy voting "to PGI or to that Fund's Sub-Advisor, as
appropriate", with each policy printed in an appendix, so each registrant is keyed PRINCIPAL from the
EDGAR filing date of its earliest SAI read (Principal Funds, Inc. 898745, 2021-02-24,
0000898745-21-000179; Principal Exchange-Traded Funds 1572661, 2021-04-26, -21-000034; Principal
Variable Contracts Funds 12601, 2021-04-28, 0000012601-21-000065) and the exceptions are listed per
series. A series is EXTERNAL when ANY SAI read names an unaffiliated sub-adviser for any portion of
it (12 Principal Funds series and 1 Variable Contracts account); Spectrum Asset Management (own
printed policy) is keyed SPECTRUM for the two Spectrum preferred funds and two ETFs and Origin Asset
Management LLP ORIGIN for the Origin Emerging Markets Fund while the SAIs name it (to 2024-12-26,
UNRESOLVED after); the LargeCap S&P 500 Managed Volatility Index Account (a Spectrum sleeve inside a
PGI account) is UNRESOLVED; Principal Real Estate Investors is covered by the PGI policy (its heading
names PGI and Principal Real Estate Investors from the 2021-10-27 SAI) so its series are PRINCIPAL from
then. The Principal Real Asset Fund (1756404, a multi-sub-adviser interval fund) is ingested but not
keyed, because its N-CSR names no sub-adviser. Ingested N-PX 2024-26 (non-duplicate votes: 305,463
Principal Funds, 73,365 Variable Contracts, 30,736 ETFs, 7,259 Real Asset Fund). Not ingested: the
institutional-manager N-PX of Principal Global Investors (769734) and Principal Real Estate
Investors (1218333), which overlap the fund tables; the Principal Real Estate Income Fund
(1557523), whose adviser is ALPS Advisors, Inc.; the private and interval funds with no vote table.

PGIM (PGIM Investments LLC and its subadvisers, Prudential Financial; added 2026-11-19): unlike the
other managers, no PGIM registrant has one voter. Every SAI of the 29 SAI-filing trusts says "The Board has
delegated to the Manager [PGIM Investments LLC] the responsibility for voting any proxies ... The Manager delegates to
the Fund's subadviser(s) the responsibility for voting proxies" and prints each subadviser's own policy in "Appendix
I: Proxy voting policies of the subadviser"; the five closed-end funds' N-CSR say the same of the Fund's subadviser. So
the registry keys every SERIES (`series_adviser`) by its voting subadviser, read from the trust's own Form N-CEN
(Item C.3, sub-advisers per series; every N-CEN filed 2023-01 to 2026-11 for the 34 registrants), because the SAIs name the
subadvisers only in prose and one SAI covers several funds. Keys: `JENNISON` (Jennison Associates LLC), `PGIM_QUANT`
(PGIM Quantitative Solutions LLC, formerly QMA LLC) and `PGIM_INC` (PGIM, Inc. with PGIM Limited and PGIM Real Estate (UK)
Limited: the SAIs print one "PGIM, Inc." appendix for its investment groups, PGIM Fixed Income and PGIM Real Estate among
them, so those are one key, not two); any unaffiliated subadviser named for any part of a series makes it `EXTERNAL`
(Prudential Series Fund and Advanced Series Trust portfolios run by J.P. Morgan, T. Rowe Price, Wellington, MFS,
ClearBridge and others); two different PGIM voters in one series, an affiliate whose policy no SAI prints (PGIM Wadhwani,
PGIM DC Solutions) or a subadviser change inside the window (the Target Date funds, PSF Global Portfolio, PGIM Portfolio
Ballast ETF) is `UNRESOLVED`; a series with no subadviser, or absent from every N-CEN read, stays unlabelled. N-CEN's
affiliated flag is not trusted over the firm's name (a few rows flag Jennison or PGIM Limited as unaffiliated). Rules start
on the filing date of the first N-CEN read for the series, so meetings before 2023 stay unlabelled (the ledger holds
votes from 2023-07 only). Policy text: the Jennison Proxy Voting Policy and Procedures PDF on jennison.com (200,
`application/pdf`, honest client, probed 2026-11-19; Wayback holds one capture of it), plus the three affiliates' policies
as printed in an SAI: Jennison (Prudential Jennison Blend Fund, six editions 2021-2026), PGIM Quantitative Solutions
(Target Portfolio Trust, five) and PGIM, Inc. (Prudential Investment Portfolios 4, five). PGIM Quantitative Solutions and
PGIM, Inc. publish no stand-alone policy (their pages are overviews saying it is available on request), and the SAI prints
a description of those two, with the PGIM, Inc. text differing by trust; the SAI-printed Jennison text can leave a stray
page number inside a sentence. Ingested N-PX 2024-26: 1,034,699 non-duplicate votes (Advanced Series Trust alone 672,550,
almost all EXTERNAL; no duplicate group left in the PGIM CIKs). Not ingested: the municipal and money-market trusts, PGIM
Securities Investment Trust Enterprise (1666044), PGIM Private Credit Fund (no N-PX), the PGIM institutional-manager and
private / collective-trust / offshore funds, and the legacy-HTML N-PX before 2024.

Victory Capital (Victory Capital Management Inc., with the Pioneer funds acquired from Amundi Asset Management
US, Inc.; added 2026-11-19): every Victory SAI says "The Proxy Voting Policy delegates to the Adviser the obligation
to vote the Funds' proxies ... subject to oversight by the Board", the Adviser being Victory Capital Management Inc.
(its franchises RS, Sycamore, Munder, Integrity, Trivalent, NewBridge, Sophus and USAA are teams of that one
adviser), so Victory Portfolios, II, III (formerly USAA Mutual Funds Trust) and the Variable Insurance Funds are keyed
`VICTORY` from the filing date of the earliest SAI read (2021-02-05 to 2021-09-28). Exceptions are per series and
come from each trust's Form N-CEN Item C.3 (every N-CEN 2021-06 to 2026-11) plus the SAI sentence that says the
sub-adviser votes (USAA trust: "the Manager has delegated responsibility for voting to the applicable subadvisers";
Victory Portfolios and Variable Insurance Funds: "Park Avenue [and] SailingStone is authorized to vote proxies"): `EXTERNAL`.
Park Avenue's series are EXTERNAL to 2023-12-31 (last N-CEN naming it), `UNRESOLVED` from 2024-01-01 (the April
2024 SAIs still name it, the N-CEN of FY2024 does not) and `VICTORY` from the first SAI that no longer names it
(2025-04-25 / 2025-04-14). The Pioneer funds are the non-obvious part. Their SAIs (2021) say "Each of the Pioneer
Funds ... have delegated responsibility to vote proxies ... to Amundi US", under Amundi US's own policy, so every
Pioneer registrant is keyed `AMUNDI_US` to 2025-03-31 and that key is never paired with a Victory policy. On 2025-04-01
Amundi US was combined with Victory Capital Holdings; the Pioneer funds' advisory agreements terminated and an interim
advisory agreement with Victory Capital took over (497 supplement of 2025-04-01), but no document read says whose
proxy policy voted the meetings of the following weeks, so they are `UNRESOLVED` until the registrant's own first
Victory document: the first Victory Portfolios IV SAI (2025-07-25; its N-PX of 2025 reports the predecessor funds' votes
from 2024-07-01, so three eras sit in one table and are separated by meeting date), the first Variable Insurance Funds
II SAI (2026-04-29), or the closed-end fund's first N-CSR that prints Victory's H-12 policy (Pioneer Diversified High
Income 2025-07-09, Pioneer High Income 2026-06-04; Pioneer Floating Rate none). The Pioneer trusts that kept their
own CIK reported only to 2024-06-30 (two filed a 2025 notice report pointing nowhere) and carry `npx_ended`; they
are ingested under this institution because the registrants now belong to Victory, but their votes are not Victory's:
the key keeps them apart in the engine. Policy text: Victory Capital publishes only a one-page "Proxy Voting Guidelines"
memo a year (vcm.com/assets/policies, 200 `application/pdf` to honest clients, probed 2026-11-19; 2022, 2023, 2024,
2025 and 2026 editions, the file name changing each year, walked on the Wayback index under one label); the full policy
H-12 (`H-12 Proxy Policy.pdf`) answers 404 on vcm.com and investor.vcm.com (two 2021 Wayback captures exist and are not
archived). Under separate labels: the Adviser's summary as printed in the Victory Portfolios II SAI (13 prints
2021-2026, which alternate because SAIs of different fund sets filed the same month carry different editions and
typesetting: read them as per-SAI prints, not as an edit history), Victory's H-12 policy as printed in Item 7 of the
Pioneer Diversified High Income Fund N-CSR (2025-07-09), and Amundi US's policy as printed in Appendix B of the Pioneer
Fund SAI (two editions, 2021 and 2023; the running "Table of Contents" links, the run of page numbers and the SAI's
document code are removed). Ingested N-PX 2024-26: 637,837 non-duplicate votes (VICTORY 550,761, EXTERNAL 52,364,
AMUNDI_US 20,709, UNRESOLVED 14,003; 1,133 duplicates marked). Not ingested: the Pioneer municipal and money-market
registrants, the two insurance-linked interval funds, the institutional-manager N-PX of Victory Capital Management
and Amundi US, and the legacy-HTML N-PX before 2024.

Thrivent (Thrivent Asset Management, LLC and Thrivent Financial for Lutherans; added 2026-11-19): every Thrivent SAI says
"The Board has delegated to [Thrivent Financial / Thrivent Asset Mgt. / the Adviser] ... the responsibility for voting any
proxies with respect to each Portfolio [Fund] in accordance with the proxy voting policies adopted by [it]". The two
Thrivent entities adopted one policy "collectively", so Thrivent Series Fund, Thrivent Mutual Funds, Thrivent Core Funds
and Thrivent ETF Trust are keyed `THRIVENT` from the filing date of the earliest SAI read (2021-02-26 to 2022-10-03; the
ETF Trust's first SAI is the 497 of its effectiveness). The non-obvious part is the subadvisers: until 2023 the SAIs add
"The Board has authorized the Adviser to delegate ... its proxy voting authority to a Portfolio's subadviser ... a
subadviser who has delegated authority ... does so in accordance with proxy voting policies adopted by the subadviser",
and Appendix A prints Goldman Sachs Asset Management's, Aberdeen's and BlackRock's policies. The Form N-CEN (every one
2021-01 to 2026-03) names the subadviser of three Series Fund portfolios (International Allocation, Partner Emerging
Markets Equity, Partner Healthcare) and of the Mutual Funds International Allocation Fund. Those series are `EXTERNAL`
while an SAI and the N-CEN name the subadviser (the N-PX does not split a sleeve, so a partly subadvised series is
EXTERNAL whole): to 2022-12-31 for the Series Fund, to 2023-04-30 for the Mutual Funds fund ("until April 30, 2023" in
its SAI). The Series Fund portfolios are `UNRESOLVED` from 2023-01-01 to 2023-04-27 (the N-CEN period ends 2022-12-31,
the SAI of 2023-04-28 is the first to name no subadviser) and THRIVENT afterwards; these windows precede the first
ingested meeting (2023-07-04), so every ingested vote is THRIVENT. Policy text: Thrivent publishes no stand-alone
proxy voting policy (its responsible-investing page names "Thrivent's Proxy Voting Guidelines" without a link and the
SAI says the detailed guidelines are available to clients on request; no Wayback capture of any such address), so the
only public text is the summary printed as Appendix A of the SAI, archived from the Thrivent Mutual Funds multi-fund SAI
as 6 versions (2021-2026). The Series Fund, Core Funds and ETF Trust SAIs print the same summary and are not mixed in.
Ingested N-PX 2024-26: 693,860 non-duplicate votes (1,068 duplicates marked). Not ingested: Thrivent Cash Management
Trust (notice-only N-PX), Thrivent Church Loan and Income Fund ("did not hold any votable positions"), Thrivent
Financial for Lutherans' institutional-manager N-PX and the legacy-HTML N-PX before 2024.

Dodge & Cox (added 2026-11-19): the only US fund registrant filing N-PX vote tables is Dodge & Cox Funds (CIK 29440, seven
series); the older single-fund CIKs (Stock Fund 29442, Income Fund 836427) stopped filing in 2007. Every SAI says "The
Dodge & Cox Funds have authorized Dodge & Cox to vote proxies on behalf of the Dodge & Cox Funds pursuant to the following
Dodge & Cox Proxy Voting Policies and Procedures" (Appendix B), and none of the six Form N-CEN read (FY2020 to FY2025)
names a sub-adviser, so the trust is keyed `DODGE_COX` from the EDGAR filing date of the earliest SAI read (2021-01-08, the
Emerging Markets Stock Fund 485BPOS) with no series exception. Policy text: the dodgeandcox.com Funds policy PDF (3
versions, 2022-2026) and the same policy as printed in the multi-fund SAI (6 versions, 2021-2026); the 2021-01-08 SAI is a
single-fund family printing an older edition and is not mixed in. The original 2026 N-PX is marked duplicate because its
N-PX/A restates every vote. Ingested N-PX 2024-26: 25,757 non-duplicate votes (9,098 duplicates marked). Not ingested:
Dodge & Cox's institutional-manager N-PX and the legacy-HTML N-PX before 2024.

First Trust (added 2026-11-19): twelve open-end registrants file N-PX vote tables with operating-company votes (First Trust
Exchange-Traded Fund I to VIII, the two AlphaDEX trusts, First Trust Series Fund, First Trust Variable Insurance Trust; ETF V
and VII file notice reports only). Every SAI says "The Board has delegated to First Trust the proxy voting responsibilities"
and that First Trust uses ISS for recommendations and execution, so ISS executing the votes does not decide the key; what
the SAI says the policy is does. The earliest SAIs read (2021-01-15 to 2021-11-24) say "First Trust has adopted the ISS Proxy
Voting Guidelines" and attach ISS's own guideline book as the exhibit: those meetings are keyed `FIRST_TRUST_ISS`, a key that
does not claim the policy is First Trust's own. From the SAI that first says "The First Trust Proxy Voting Guidelines
[Policies and Procedures] are attached hereto" (First Trust Advisors L.P.'s own written policy; 2022-09-30 to 2023-04-28,
per trust, and no later SAI reverts) the trust is keyed `FIRST_TRUST`. A series whose OWN single-fund SAI says the Board
delegated day-to-day voting to a sub-adviser (Vest, WCM, Energy Income Partners, Janus Henderson, Confluence, First Trust
Capital Management) is `EXTERNAL`; the multi-fund annual SAIs list every series of the trust and say First Trust, but the
own SAI is the more specific statement and the N-CEN names the same sub-adviser. A series whose N-CEN names a sub-adviser
while every SAI says First Trust votes keeps the registrant key. ISS's own guideline book (the exhibit of the 2021-22 SAIs)
is copyrighted and not archived; the policy archive is First Trust's own text as printed in the ETF V SAI (6 versions in 3
labels, one per era and one for Exhibit B). The 2026 N-PX/A of four trusts restate every vote with corrected shares, so
56,909 original lines stay non-duplicate beside the amendment's lines (summing shares for those four filings double-counts;
see ROADMAP). Ingested N-PX 2024-26: 674,170 non-duplicate votes (44,779 duplicates marked). Not ingested: the closed-end
funds, the FT Vest series funds, First Trust's private-credit funds, First Trust Advisors' institutional-manager N-PX and the
legacy-HTML N-PX before 2024.

VanEck (added 2026-11-20): three open-end registrants file N-PX vote tables with operating-company votes (VanEck ETF Trust,
VanEck Funds, VanEck VIP Trust). Every SAI read (2021-2026) says "Proxies for each Fund's portfolio securities are voted in
accordance with the [applicable] Adviser's proxy voting policies and procedures, which are set forth in Appendix A", and
Appendix A is VanEck's own policy: VanEck engaged Glass Lewis for research, recommendations and vote execution, has reviewed
the Glass Lewis guidelines and "generally follows" them, and "retains the right, on any specific proxy, to vote differently".
Because the policy belongs to VanEck and Glass Lewis only executes it, the trusts are keyed `VANECK` (contrast First Trust,
whose early SAIs say the adviser adopted ISS's guidelines and are keyed `FIRST_TRUST_ISS`), from the earliest 2021 SAI read.
The SAI names a sub-adviser only for the China funds, and says only that it places orders, so no series exception is made
(see ROADMAP). Policy text: Appendix A as printed in the VIP Trust SAI (1 version, unchanged 2021-2026); the Glass Lewis
guideline book that follows it in each SAI is copyrighted and not archived, and vaneck.com has no US policy page. Ingested
N-PX 2024-26: 108,669 non-duplicate votes (32,808 duplicates marked, most of them the 2024 ETF Trust N-PX superseded by its
N-PX/A). Not ingested: VanEck CLO Opportunities Fund, VanEck Associates' institutional-manager N-PX and the legacy-HTML N-PX
before 2024.

WisdomTree (added 2026-11-20): two open-end registrants file N-PX vote tables (WisdomTree Trust, WisdomTree Digital Trust).
Every SAI read (2021-2026) says "The Trust has adopted as its proxy voting policies for each Fund the proxy voting
guidelines of each Fund's applicable Sub-Adviser. The Trust has delegated to the Sub-Advisers the authority and
responsibility for voting proxies", and the Form N-CEN of 2021-2026 lists an unaffiliated sub-adviser (Mellon, Voya IM,
Newton, Insight North America) for all 117 series. WisdomTree Asset Management therefore votes no series itself and has no
proxy voting policy to key or archive: both trusts are keyed `EXTERNAL` from the earliest SAI read, and the sub-advisers'
policies printed in the SAI are not archived as WisdomTree's (EXTERNAL votes are never paired with a policy document;
`policy_in_force` answers `none_in_force`). Source access: wisdomtree.com answers honest clients with 403 on every address
tried (2026-11-20), so nothing was read from it; it is not evaded. Ingested N-PX 2024-26: 917,066 non-duplicate votes
(587,555 marked, most of them originals superseded by N-PX/A). Not ingested: WisdomTree Ethereum Trust and the legacy-HTML
N-PX before 2024.

Global X (added 2026-11-20): one open-end registrant files N-PX vote tables (Global X Funds). Every SAI read (2021-2026) says
"The Funds have delegated proxy voting responsibilities to the Adviser" and that "the Adviser has adopted proxy voting
policies and guidelines for this purpose", which "have been adopted by the Trust"; Glass Lewis "is responsible for the actual
voting" and votes per its recommendations "overseen by the Advisor" unless the Adviser gives "different direction". The policy
is Global X's own and Glass Lewis executes it (the SAI never says the Adviser adopted Glass Lewis's guidelines), so the trust is
keyed `GLOBAL_X` from the earliest SAI read, as VanEck is and unlike First Trust's early `FIRST_TRUST_ISS` period. No SAI says
a sub-adviser votes, so there is no series exception. Policy text: Parts I and II of the SAI voting statement (1 version,
unchanged 2021-2026); Glass Lewis's own guidelines are not archived. Sixteen series that the SAIs name under a Catholic or ESG voting-policy addendum (not printed, so not held) are keyed `GLOBAL_X_CATHOLIC` / `GLOBAL_X_ESG` for the window the SAIs support and `UNRESOLVED` outside it, never paired with the general text. Source access: globalxetfs.com answers honest clients with
429 on every address tried, robots.txt included (2026-11-20), so nothing was read from it; it is not evaded. Ingested N-PX
2024-26: 374,527 non-duplicate votes (127,201 marked, most of them the original 2024 N-PX superseded by its same-day N-PX/A).
Not ingested: Global X Venture & Innovation Fund, the Canadian and Japanese Global X managers and the legacy-HTML N-PX before 2024.

ProShares (added 2026-11-20): two open-end registrants file N-PX vote tables, ProShares Trust (adviser ProShare Advisors LLC) and
ProFunds (adviser ProFund Advisors LLC). Every SAI read (2021-2026) says the Board delegated voting to the adviser and attaches
one joint written policy for both advisers ("collectively, the Advisor"), under which proxies are generally voted in accordance
with the ISS Guidelines that ISS "maintains and implements"; the Advisor "reserves the right to modify any of the
recommendations". The document is the advisers' own, so both trusts are keyed `PROSHARES` from the earliest 2021 SAI read (one
key for one policy, not one per legal entity), as First Trust's own written policy is `FIRST_TRUST` and not `FIRST_TRUST_ISS`. No
SAI names a sub-adviser that votes or an addendum, so there is no series exception. Policy text: Appendix C of the ProShares Trust
SAIs (1 version, unchanged 2021-2026) and the short form on proshares.com and profunds.com (honest clients get 200; archived
from the Wayback Machine back to 2022); ISS's own guidelines are not archived. Ingested N-PX 2024-26: 1,000,718 non-duplicate
votes (13,687 marked, exact repeats inside an exhibit). Not ingested: Access One Trust and the legacy-HTML N-PX before 2024.

New York Life Investments (added 2026-11-21): six open-end and closed-end registrants file N-PX vote tables with
operating-company votes (NYLIM Funds, NYLIM Funds Trust, NYLIM VP Funds Trust, NYLIM ETF Trust, NYLIM Active ETF Trust,
NYLIM CBRE Global Infrastructure Megatrends Term Fund; formerly MainStay and IndexIQ). Multi-policy keying: the SAIs say the
Board delegated all voting to the Manager, which "has adopted its own Proxy Voting Policies and Procedures" and "may
delegate proxy voting authority to the Subadvisor", and then name, fund by fund, who it delegated to and which funds it
retained. There is therefore no registrant-wide voter and each series is keyed by the voter the SAI names, from the EDGAR
filing date of the first SAI that names it: `NYLIM` (the Manager and the funds it retained, including the fund-of-funds
allocation series whose votes are on registered funds), the affiliates that vote under their own policy (`MACKAY_SHIELDS`,
`NYL_INVESTORS`, `CANDRIAM`, `INDEXIQ`, `AUSBIL`), and `EXTERNAL` for unaffiliated sub-advisers (Epoch, Winslow, Wellington,
CBRE, Cushing, Fiera, PineStone and others). Affiliation comes from Form N-CEN (`isSubAdviserAffiliated`), never a date.
Anything the SAI does not settle is `UNRESOLVED`: series with several voters in one vote table (Income Builder, Balanced),
series never named (WMC Value, WMC Small Companies) and the days between two SAIs when the voter changes (S&P 500 Index,
Hedge Multi-Strategy, ESG Multi-Asset). The ETF Trust has one voter, the Advisor: `INDEXIQ` until 2024-08-26, `NYLIM` from
the SAI of 2024-08-27 (NYLIM's own ADV dates the merger 2024-09-12, so about two weeks of meetings may carry `NYLIM`).
Policy text: NYLIM's, NYL Investors' and IndexIQ's own PDFs (IndexIQ's now answers 404 and is Wayback only; honest clients
get 200 for the others), the Manager's guidelines as printed in the Funds, Trust and VP SAIs (3, 4 and 3 versions; wording
differences that are only typography are declared reprints) and the MacKay Shields summary printed in the SAIs (1 version).
ISS's own guidelines are never archived as the manager's. Not ingested: the MacKay muni closed-end funds, NYLIM's and
IndexIQ Advisors' institutional-manager N-PX and the legacy-HTML N-PX before 2024.

## Say-vs-do analysis (legacy line-level engine)

The engine connects each institution's **commitment (SAY)** to its **voting
record (DO)** on a theme, as a quantified, cited result. It is an
investigative *assist*, not an oracle — every output is a quarantined **lead**.
Precision rules, each enforced in code and tested:

- **Themes** (currently 7: climate, nature, board-diversity, labor-rights,
  lobbying-disclosure, anti-corruption, human-rights) are matched **lexically**
  against proposal text and policy text. Lexical matching means cross-theme
  overlap is possible (a "lobbying alignment with climate goals" proposal hits
  both) — the proposal text is always shown so a human judges. Researchers can
  also test **custom keyword** hypotheses.
- **Binding-commitment guard.** A policy sentence may anchor a claim only if it
  is real prose (not a PDF table-of-contents / title-case list), the manager is
  binding *itself* (first-person / fund agent), and it contains an actual
  commitment verb — not a description of an issue or an expectation of
  *companies*.
- **Polarity guard.** Voting AGAINST a proposal is a gap only if the proposal
  *advances* the theme. Anti-ESG / anti-DEI proposals ("cease/revisit/reconsider
  DEI", "report on the risks **of** DEI", counter-reports, "risks to
  beneficiaries" framings) are excluded — voting them down is consistent, not
  hypocritical.
- **Temporal alignment.** A vote is compared only to the policy version in force
  **at or before** the vote date — never a later commitment.
- **AUM = managed / voting AUM.** Coverage weighting uses the assets a manager
  actually votes, never balance-sheet, custody, or divested-arm assets.
- **OFAC SDN name-joins are excluded** from enforcement leads: a sanctions
  *designation* names who is sanctioned; matching a tracked manager or a held
  issuer to one by name alone is the documented [Aldar] false-positive class.

## Entity resolution

Join keys in strict priority order:

1. **CUSIP** (exact)
2. **LEI** (exact; fund-side LEIs from N-PX covers, GLEIF free API)
3. **CIK** (exact)
4. **Normalized-name fuzzy match** — token-set similarity with legal-suffix
   stripping and a length-ratio guard. Threshold 0.85 for any join used in a
   finding. **Every fuzzy match is logged** (query, candidate, score,
   accepted/rejected) in the `match_log` table.

Precision is preferred over recall throughout: a false accusation is fatal;
a missed match is acceptable.

## Data sources (Phase 1)

| Source | What | Access |
|---|---|---|
| SEC EDGAR N-PX | Proxy voting records (vote-level XML exhibits) | Free API, User-Agent required |
| SEC EDGAR 13-F | Quarterly institutional holdings | Free API |
| DOJ FCPA related-enforcement pages (a–z) | FCPA corporate resolutions | Free, HTML |
| OFAC SDN + consolidated list | Sanctions designations | Free bulk CSV |
| World Bank debarred firms | Procurement debarments | Free API |
| UN Global Compact | Expelled participants | Free API |
| SEC EDGAR N-PORT | Monthly mutual-fund portfolios (extends beyond 13-F filers) | Free API |
| Federal Reserve enforcement actions | The banks' own records (administrative actions, bulk CSV) | Free CSV |
| EPA ECHO (`case_downloads.zip`) | Environmental enforcement cases (weekly bulk CSV dump) | Free bulk zip |
| CourtListener / RECAP | Federal dockets — **allegations only, never findings; score zero** | Free API |
| Curated snapshots (predecessor project, extracted 2026-05-26) | FCPA, SEC fraud, DOJ antitrust, World Bank, NLRB, UNGC | Hand-verified; re-verification required |

All sources are free and public. No paid APIs are used anywhere.

Source-access notes (probed 2026-06-11): the World Bank debarment API and
CFPB enforcement pages reject non-browser clients at the CDN; the UNGC
participants JSON endpoint and the SEC litigation-release RSS URL both moved
or now serve HTML. Glasshouse does not impersonate browsers to evade CDN
rules — blocked sources stay on curated snapshots until a sanctioned access
path (bulk download, official API) is found.

### EPA ECHO parsing notes (added 2026-07-16)

Scope is deliberately narrow, precision-first:

- Only defendants whose **normalized name exactly equals** a company on the
  hand-verified fossil-fuel list (`fossil.py`). Subsidiaries (e.g. "BP
  Products North America") do **not** match parents ("BP plc") — parent
  attribution is a human judgment, so the ingest undercounts rather than
  guesses.
- Only **concluded** cases: assessed penalty > 0, a case-status date, and the
  defendant named in the settlement. This excludes open matters and multi-PRP
  Superfund pileups where a major appears among dozens of parties with no
  penalty of its own.
- Judicial → `civil_violation`; administrative → `administrative_action`;
  criminal cases are **skipped** (outcome semantics are ambiguous in bulk).
- `company_name` is the defendant **as filed**; every row carries the ECHO
  case-report URL and case number. The bulk file is EPA's own weekly dump —
  no scraping, no keys.

### N-PX parsing notes (validated 2026-06-10)

- Vote tables are separate XML exhibits in the filing directory (65–124 MB),
  namespace `http://www.sec.gov/edgar/document/npxproxy/informationtable`;
  parsed with a streaming parser (lxml `iterparse`), never regex.
- `primary_doc.xml` is the cover page: series IDs, names, LEIs. Filings with
  `reportType = FUND NOTICE REPORT` are cover-only notices with no votes.
- One `proxyTable` may contain **multiple** `voteRecord` elements; all are
  parsed.
- **Duplicate vote records are endemic in N-PX as filed** (found 2026-06-11
  during an editorial audit): the same voteRecord repeated within one
  exhibit (one copy per share class) and the same series' votes filed in
  two exhibits of the same period — 107,088 of 2,158,394 ingested rows
  (9.3% of rows — 350,732 of 3,765,999 as of 2026-11). Rows are kept as filed but marked `is_duplicate`; every analytic
  query excludes them. N-PX ingest re-runs the marking before it returns, and `glasshouse release` and `glasshouse doctor` refuse/err when any vote is newer than the last dedupe run. **Never sum `shares_voted` without this filter.**
  A run cut short by `--max-tables` marks that filing `partial` and the next normal ingest replaces its votes; `glasshouse ingest npx --reingest <accession,...> --reason "..."` does the same for named filings and logs the reason in `ingest_runs`.
  Rows where identical share counts appear FOR and AGAINST the same
  proposal are additionally excluded from divergence visuals as likely
  as-filed duplication, pending verification.
- `managementRecommendation` values look inconsistent with proxy-statement
  norms in some rows (e.g. "FOR" on shareholder proposals). Glasshouse
  reports the field verbatim with its accession; any published claim that
  leans on the management recommendation must first be verified against the
  issuer's proxy statement.

### Legacy N-PX, July 2022 – June 2023 (quarantined; added 2026-11-22)

Before the XML form (votes from July 2023), N-PX was free text. The 2022-23 year is
being read from three filer layouts: Broadridge ProxyEdge text, ISS "FORM N-Px REPORT"
text, and ISS HTML tables. Research notes: `docs/research/legacy-npx.md`.

- **Two parsers, one answer.** Each layout is read by two parsers written independently
  from one written contract. A row is kept only when both produce it identically over
  all 14 fields (fund heading, issuer, ticker, security ID, meeting date and type,
  record date, recommendation column, proxy card, proposal number and text,
  recommendation, vote, sponsor). If the parsers disagree on more than 0.5% of a
  filing's rows, the whole filing is rejected (`report_type` ending `_REJECTED`) and
  nothing from it is inserted. Per-document agreement counts are in the `legacy_parse`
  table.
- **Fund → series** only through the filing's own SGML header: exact normalised name
  match, or one trailing " - SUFFIX" removed. Trademark marks ("(R)", "(SM)", "(TM)",
  ®, ™, ℠) are removed from both sides first. Failing that, a heading may map through
  `config/legacy_series_aliases.csv`: 298 hand-reviewed (registrant CIK, heading) →
  series entries, e.g. John Hancock's "3347 JHFII …" codes, "CREF Stock" → "Stock
  Account", "T. Rowe Price"/trust-name prefixes. An alias counts only if its series is
  listed in that filing's own header. No fuzzy matching. A heading that still does not
  match is dropped and counted, so recall is knowingly incomplete.
- **Dropped on purpose:** proxy-contest rows (two cards, so the management
  recommendation is undefined); votes outside a closed vocabulary (e.g. "None", "N/A",
  "Take No Action"); unknown sponsors; unparseable meeting dates.
- **Columns.** `legacy_format` is `proxyedge`, `iss_text` or `iss_html` (NULL for XML
  rows). `shares_voted` is NULL: these formats print no share counts.
  `management_recommendation` is set only under a "Mgt Rec" column.
  `for_against_management` comes only from ProxyEdge, which prints it; it is NULL
  elsewhere and never derived.
- **Quarantine.** Legacy rows are in the ledger but excluded from releases and every
  analytic read (`ledger.NON_LEGACY_VOTE_SQL`) until a reviewer pass and a hand sample
  against the source filings support promoting them.

## Scoring — the Concern Index (v0)

For a company's set of resolved enforcement actions:

```
concern_raw = recidivism × Σ severity(resolution_type) × 0.5^(age_years / 5)
score       = 100 × (1 − e^(−concern_raw / 20))
```

- **Severity** (fixed table, anchored to legal weight): guilty plea 10,
  sanction designation 9, DPA 7, NPA 6, debarment 6, civil settlement 5,
  civil violation / board order 4, administrative 3, expulsion 2.
  **Allegations and unverified records score zero** — quarantined data
  never moves a score.
- **Recency**: 5-year half-life; undated actions are discounted as if 10
  years old.
- **Recidivism**: × (1 + 0.15 × (n − 1)), capped at 2.0.
- Duplicate-marked rows are excluded before scoring.

Every score is reproducible from the public ledger
(`glasshouse report concern --company X` prints the full per-action
breakdown). The index is an analytical summary of public records, not a
legal finding. **v0 limitation:** no confidence intervals on gapped data
yet; scores on companies with sparse coverage understate, never overstate,
because absent records contribute nothing.

## Limitations

- 13-F captures only long US equity positions of managers above $100M AUM;
  shorts, derivatives, fixed income, and non-US positions are excluded.
- N-PX reporting periods are annual (July–June), filed by end of August;
  vote data lags the meeting by up to 14 months.
- Curated snapshot data may be stale; entries are marked and re-verified
  before use in claims.
- Fuzzy name matches below threshold are never used in findings.
- GLEIF's ISIN→LEI mapping is opt-in for LEI issuers and therefore partial
  (strong for US/EU issuers, sparse elsewhere — e.g. Aldar Properties PJSC's
  UAE ISIN is unmapped as of 2026-06-11). Issuers without an LEI stay
  name-only leads.
- **Even exact normalized-name matches are only leads.** Validated on the
  first live run (2026-06-11): OFAC's "ALDAR PROPERTIES" (Sudan, SDGT
  program) normalizes identically to Aldar Properties PJSC (Abu Dhabi-listed
  developer) — two different companies. A vote×enforcement join becomes
  finding-grade only with identifier corroboration (CUSIP/LEI/CIK) or human
  verification of the primary source.
- An enforcement action against a held company is not evidence that the
  holder knew of, endorsed, or profited from the conduct. Glasshouse reports
  the conjunction of documented facts; it does not characterize motive.

## Roadmap

1. **Phase 1 (current):** N-PX ingestion, entity resolution, evidence ledger,
   first enforcement sources. Public repo.
2. **Phase 2:** Commitments ledger (scrape + version + Wayback history).
3. **Phase 3:** Contradiction + diff engines → first 10 vote-contradiction
   findings published manually. **Demand test:** audience response reviewed
   before Phase 4 and allowed to re-rank everything after.
4. **Phase 4:** Interfaces — static site, Datasette, RSS, email digest, MCP.
5. **Phase 5:** Daily enforcement/news event trigger + alert path.
6. **Phase 6:** Publicist agent (human-gated approval queue), non-response
   ledger, fiduciary-channel and coalition drafts.
7. **Phase 7:** 13-F/N-PORT expansion + first annual awards cycle.

At each phase boundary: ship publicly, post what's new, record the response,
re-prioritize on distribution evidence — audience signal is a first-class
input, not vanity metrics.
