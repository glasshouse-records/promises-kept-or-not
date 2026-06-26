"""Legacy (pre-2024) N-PX HTML parser — historical vote depth.

The SEC's structured/machine-readable N-PX rule only covers periods ending
~mid-2024. Earlier filings are HTML. The dominant format (ISS/Broadridge) is,
fortunately, regular tables: one <table> per security, with

    <td colspan=5>ISSUER NAME <br/> MEETING DATE:  MON DD, YYYY</td>
    <td colspan=5>TICKER:  XXX   SECURITY ID:  CUSIP</td>
    <th>Proposal No</th><th>Proposal</th><th>Proposed By</th>
        <th>Management Recommendation</th><th>Vote Cast</th>
    <td>1</td><td>...</td><td>Management</td><td>For</td><td>For</td>
    ...

PRECISION IS CARDINAL (a false vote is fatal): we emit a row ONLY when a
security header (issuer + CUSIP), a recognizable 5-column header, and a
well-formed proposal row are all present. Anything ambiguous is dropped, not
guessed. Votes produced here are tagged (vote_source='legacy_html') so they
stay quarantinable and out of the public release until validated.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime

from lxml import html as lxml_html

from .edgar import Filing, filing_directory
from .npx import VoteRow

# The canonical legacy column order. We verify the header matches before
# trusting positional cells.
_EXPECTED_HEADER = ["proposal no", "proposal", "proposed by",
                    "management recommendation", "vote cast"]
_MEETING_RE = re.compile(r"MEETING DATE:\s*(.+)", re.I)
_SECID_RE = re.compile(r"SECURITY ID:\s*([A-Za-z0-9]+)", re.I)
_VALID_VOTE = re.compile(r"[A-Za-z]")  # a vote must contain a letter (For/Against/…)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def _norm_date(raw: str) -> str:
    """'JUN 29, 2023' → '06/29/2023'. Returns '' if unparseable (never guess)."""
    raw = _clean(raw)
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%m/%d/%Y")
        except ValueError:
            continue
    return ""


def find_legacy_vote_docs(filing: Filing) -> list[str]:
    """URLs of the HTML documents in a legacy filing that may hold vote tables
    (excludes EDGAR index/header pages)."""
    urls = []
    for item in filing_directory(filing):
        name = item.get("name", "")
        low = name.lower()
        if not low.endswith((".htm", ".html")):
            continue
        if "index" in low or "header" in low:
            continue
        urls.append(f"{filing.directory_url}/{name}")
    return urls


def iter_legacy_vote_rows(html_bytes: bytes) -> Iterator[VoteRow]:
    """Yield one VoteRow per well-formed proposal in a legacy N-PX HTML doc."""
    doc = lxml_html.fromstring(html_bytes)
    for table in doc.iter("table"):
        issuer = cusip = meeting = ""
        header_ok = False
        for tr in table.iter("tr"):
            cells = tr.findall("./td") + tr.findall("./th")
            texts = [_clean(c.text_content()) for c in cells]
            joined = " ".join(texts)

            # security header rows (single wide cell)
            if "MEETING DATE:" in joined.upper() and len(cells) == 1:
                # "ISSUER ... MEETING DATE: DATE"
                m = _MEETING_RE.search(joined)
                meeting = _norm_date(m.group(1)) if m else meeting
                issuer = _clean(joined[:joined.upper().find("MEETING DATE:")])
                continue
            if "SECURITY ID:" in joined.upper():
                m = _SECID_RE.search(joined)
                if m:
                    cusip = m.group(1).upper().strip()
                continue

            # column header row — confirm positional trust
            low = [t.lower() for t in texts]
            if low == _EXPECTED_HEADER:
                header_ok = True
                continue

            # proposal row: 5 cells, only after we've locked issuer+cusip+header
            # AND a parseable meeting date. A dateless vote signals a format the
            # parser doesn't understand — drop it (precision over recall) rather
            # than emit an undated, un-time-alignable vote.
            if header_ok and issuer and cusip and meeting and len(texts) == 5:
                num, desc, proposed_by, mgmt_rec, vote = texts
                # precision guards: a real proposal has a description and a vote,
                # and the first cell looks like a proposal number/id (not prose).
                if not desc or not vote or not _VALID_VOTE.search(vote):
                    continue
                if desc.lower() in ("proposal", "proposal no"):
                    continue
                if len(num) > 6:  # proposal "No" should be short (1, 2, 3a…)
                    continue
                yield VoteRow(
                    issuer_name=issuer,
                    cusip=cusip,
                    meeting_date=meeting,
                    vote_description=desc,
                    category_type=proposed_by,
                    vote_source="legacy_html",
                    how_voted=vote,
                    management_recommendation=mgmt_rec,
                )
