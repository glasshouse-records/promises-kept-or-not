# Hand-over: what exists, and what only you can do

Written 2026-11-17. Published the same day: the dataset on Zenodo
(first version doi:10.5281/zenodo.24321607; version 2026-11-17.2,
adding Capital Group and Dimensional, doi:10.5281/zenodo.24324314;
version 2026-11-17.3, adding Geode-voted Fidelity index series, Wellington via
Hartford and 17 more Capital Group trusts, doi:10.5281/zenodo.24326076;
version 2026-11-18, adding Nuveen/TIAA, Columbia, Parametric and 19 SAI-printed
policy versions, doi:10.5281/zenodo.24329615;
version 2026-11-18.2, adding Dimensional master funds and dated Standard/Social/
Sustainability guidelines plus four Columbia registrants, doi:10.5281/zenodo.24339801;
version 2026-11-18.3, corrected for duplicate vote lines (see docs/CORRECTIONS.md) and adding
Morgan Stanley, MFS, American Century, Janus Henderson, AllianceBernstein and Federated Hermes,
doi:10.5281/zenodo.24353272) and the code at
https://github.com/glasshouse-records/promises-kept-or-not, both credited to
"Glasshouse". Nothing else has been sent or shown to anyone; the drafts below
are still private.

## What exists

- **The record** (`data/glasshouse.db`): three full seasons of fund proxy votes
  (meetings July 2023 – June 2026), an archive of the managers' own voting
  policies with every version dated, holdings, and the enforcement record.
- **Who votes what**: for all 38 fund trusts on file, the adviser that casts
  the votes, verified from each trust's SEC prospectus — per individual fund
  and by date where it differs (Vanguard from 2026-01-12, BlackRock from
  2025-01-01). The tools refuse to compare a policy with another adviser's votes.
- **The engine** (`glasshouse ask …`): cited answers about votes and policy text.
- **The checker** (`glasshouse desk verify …`): re-checks a draft claim by claim.
- **The release bundle** (`data/releases/v2026-11-17/`): the dataset as plain
  files with checksums, the adviser map, and a datasheet. This is the thing
  a researcher would download.
- **Six verified drafts** in `data/desk/` — see below.
- **The workflow**: `docs/WORKFLOW.md`, `docs/ROADMAP.md`, `/next`,
  `scripts/gates.sh`, `scripts/routine.sh`.

## The six drafts (all unpublished leads)

| Draft | In one line | Must be checked by a person first |
|---|---|---|
| `deutsche-climate-three-seasons-2026` | DWS's US funds backed 44 of 51 shared climate proposals, then 12 of 32, then 3 of 22; lobbying support steady | Who sponsored the unflagged proposals; that DWS (not Northern Trust) votes the Equity 500 Index Portfolio |
| `director-opposition-2024-2025` | Several large managers supported clearly more board nominees in 2025 than 2024 at the same US companies; BlackRock's apparent halving was a recording change | Open the two BlackRock filings; Fidelity's 2025 season may be partial |
| `blackrock-bis-principles-2026` | The stewardship principles lost the "well below 2°C" sentence and the board-diversity disclosure request; votes barely moved | Read both PDFs; the document was largely rewritten |
| `fidelity-guidelines-october-2026` | Two long-standing sentences removed, anti-takeover rules softened, pay-dilution limits added | Read both PDFs in full |
| `ubs-policy-2026` | Numeric board-diversity rules replaced by a discretionary one; text only | PDF tables and footnotes near the diversity section |
| `t-rowe-trpa-board-composition-2026` | Board-diversity rule reworded; opposition flat. An honest non-story | Read the two PDFs |

A verified draft means every number and quotation matches the record. It does
not mean the story is fair, complete, or safe to publish. None of them says
why a manager voted as it did; the filings never do.

## What only you can do, in order

1. ~~Decide whether to publish the dataset.~~ Done 2026-11-17 (Zenodo +
   GitHub). For each new version follow `docs/PUBLISHING.md`; every push or
   upload still needs your yes.
2. **Decide about the policy documents.** The bundle ships dates, links and
   fingerprints of each policy version, not the documents. Shipping the
   managers' full texts is a copyright question; I have left it out.
3. **Decide the 175 old pending findings.** They come from the superseded
   analysis that pooled advisers. Recommendation: reject all, with that note.
4. **Decide what happens to the drafts.** Options: keep them private as proof
   the instrument works; give one to an established newsroom or research group
   to check and run under their name and legal cover; or ask the manager for
   comment first. Do not publish one yourself without a lawyer or an
   organisation behind it — that is the exposure the project was designed to avoid.
5. **Find a host or co-signer.** Earlier reviews concluded the binding
   constraint is a credible organisation, not code. The asset that is scarce is
   the dated policy archive plus the verified adviser map.
6. **Allow the daily chore.** The app refused to let me schedule
   `scripts/routine.sh`. Every day it does not run is a day a policy page can
   change uncaptured. Either allow scheduled tasks for this project or run it
   yourself: `scripts/routine.sh`.
7. **Keep copying `data/backups/` and `data/commitments/` off the laptop**
   after any day with new captures.

## Known limits (stated in the datasheet too)

- UBS, BNP Paribas and Bank of America: executive-pay votes only on file. Checked
  2026-11-17: none has a US fund trust whose votes it casts itself (UBS's PACE
  trust is voted mostly by outside sub-advisers), so this cannot be filled.
- BlackRock: 10 fund series could not be placed under either policy and are
  held apart as unresolved.
- Policy archive gaps: several advisers have a single archived version, and
  mid-year amendments between captures may be missing (Vanguard's 2022–2025
  yearly editions were recovered on 2026-11-17).
- BNY Mellon, Invesco, Northern Trust, Franklin Templeton, State Street: some
  sub-advised funds whose voting arrangements are not fully verified
  (listed as scope notes on every result).
- A ledger restored from the release bundle (`glasshouse restore`, no SEC ingest)
  has no policy text and no administrative no-vote lines; the engine says so.
  Run `ingest commitments --wayback` to get the text.
- "Country" means the country that issued the security's ISIN.

## To continue the work

Open a session in this folder and type `/next`. It reads `docs/ROADMAP.md`
and carries on.
