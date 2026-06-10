"""DOJ FCPA related-enforcement pages (a–z) → enforcement ledger.

DOJ restructured in 2024: cases live on 26 alphabetical pages at
/criminal/criminal-fraud/related-enforcement-actions-{a..z}. The index gives
case name + docket only; resolution type and penalty require the underlying
case page, so rows ingest as `unverified` (quarantined — see
PENDING_VERIFICATION.md) until verified against the case page.

Link-text parsing carried from the predecessor project (validated against
the live DOJ site there).
"""

from __future__ import annotations

import logging
import re
from datetime import date

from .. import http
from ..ledger import EnforcementAction

logger = logging.getLogger(__name__)

BASE_URL = "https://www.justice.gov/criminal/criminal-fraud/related-enforcement-actions-{letter}"

_DOCKET_YEAR_RE = re.compile(r"\b(\d{2,4})-CR", re.IGNORECASE)
_PAREN_YEAR_RE = re.compile(r"\((\d{4})\)")
_NON_CASE_STRINGS = {
    "about", "privacy", "archives", "foia", "accessibility", "vote.gov",
    "multilingual", "for employees", "social media", "signup for email updates",
    "contact usa.gov",
}


def parse_link_text(text: str) -> tuple[str, int] | None:
    """'U.S. v. BAE Systems plc: Docket No. 10-CR-035-JDB' → ('BAE Systems plc', 2010).

    Returns None for non-case link text (footer navigation etc.).
    """
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").strip()
    if not text or len(text) < 8 or "@" in text or text.lower() in _NON_CASE_STRINGS:
        return None
    if not re.match(r"(?:U\.S\.|United States)\s+v\.\s+|In\s+re\s+", text, re.IGNORECASE):
        return None

    company = ""
    m = re.match(
        r"(?:U\.S\.|United States)\s+v\.\s+(.+?)(?:\s*:\s*(?:Docket|Court)|\s*\((?:DPA|NPA|Court|Plea|\d{4}))",
        text, re.IGNORECASE,
    )
    if m:
        company = m.group(1).strip().rstrip(",")
    if not company:
        m2 = re.match(r"(?:U\.S\.|United States)\s+v\.\s+(.+)", text, re.IGNORECASE)
        if m2:
            raw = re.sub(r"\s*:\s*.*$", "", m2.group(1).strip())
            raw = re.sub(r"\s*\(.*$", "", raw)
            company = raw.strip().rstrip(",")
    if not company:
        m3 = re.match(r"In\s+re\s+(.+?)(?:\s*[\(:]|$)", text, re.IGNORECASE)
        if m3:
            company = m3.group(1).strip().rstrip(".")
    if not company:
        return None

    year = 0
    m_yr = _PAREN_YEAR_RE.search(text)
    if m_yr:
        year = int(m_yr.group(1))
    else:
        m_doc = _DOCKET_YEAR_RE.search(text)
        if m_doc:
            raw_yr = int(m_doc.group(1))
            if raw_yr > 999:
                year = raw_yr
            elif raw_yr >= 77:   # FCPA enacted 1977
                year = 1900 + raw_yr
            else:
                year = 2000 + raw_yr
    return company, year


def fetch() -> list[EnforcementAction]:
    today = date.today().isoformat()
    actions: list[EnforcementAction] = []
    seen: set[tuple[str, int]] = set()

    for letter in "abcdefghijklmnopqrstuvwxyz":
        url = BASE_URL.format(letter=letter)
        try:
            resp = http.get(url)
        except Exception as exc:
            logger.debug("DOJ FCPA page %r failed: %s", letter, exc)
            continue
        idx = resp.text.find("field_body")
        if idx < 0:
            continue
        body = resp.text[idx:idx + 50_000]
        for raw in re.findall(r"<a[^>]+>([^<]+)</a>", body):
            parsed = parse_link_text(raw)
            if not parsed:
                continue
            company, year = parsed
            key = (company.lower(), year)
            if key in seen:
                continue
            seen.add(key)
            actions.append(EnforcementAction(
                agency="DOJ (FCPA)",
                company_name=company,
                action_date=f"{year}-01-01" if year else "",
                resolution_type="unverified",   # index page lacks resolution detail
                primary_ref=raw.replace("&nbsp;", " ").replace("&amp;", "&").strip(),
                description="FCPA related-enforcement index entry; resolution type and penalty pending verification against case page.",
                source_url=url,
                retrieval_date=today,
            ))
    logger.info("DOJ FCPA: %d unique index entries", len(actions))
    return actions
