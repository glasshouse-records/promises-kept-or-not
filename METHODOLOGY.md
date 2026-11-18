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

A website HTML page whose navigation or trademark spacing changes between captures would mint phantom versions if the whole page were the text. A commitment label may therefore carry `body: {start, end}` (config/institutions.yaml): the policy text is the span from the first `start` match to the first `end` match after it, whitespace-normalised, and version identity, sentences and quote checks use only that span. A capture where either marker does not match is unreadable (never a new version, never the full page) and is logged. Currently used for American Century's website page. For every label, identity text also has whitespace removed before a trademark sign (®, ™, ©), because that spacing never changes meaning. One shared helper (`contradictions.commitment_identity`) computes identity for the engine, release, site, dataset, newsroom and timeline; the release's `policy_versions.text_sha256` is the hash of exactly that text. The ledger's own `text_sha256` is unchanged (whole page, whitespace only).
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
  Rows where identical share counts appear FOR and AGAINST the same
  proposal are additionally excluded from divergence visuals as likely
  as-filed duplication, pending verification.
- `managementRecommendation` values look inconsistent with proxy-statement
  norms in some rows (e.g. "FOR" on shareholder proposals). Glasshouse
  reports the field verbatim with its accession; any published claim that
  leans on the management recommendation must first be verified against the
  issuer's proxy statement.

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
