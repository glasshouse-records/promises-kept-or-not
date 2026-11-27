"""Regex row parser for the 2022-23 'Registrant Voted' HTML-table N-PX layout.

Implements rules H1-H9 of docs/research/legacy-npx.md ("Contract: Registrant Voted
HTML-table layout"). Approach: regular expressions pull ``<tr>`` rows and their
``<td>`` cells, then a row loop with explicit state variables reads them.
``parse(text)`` returns rows with exactly ``legacy_issueno.KEYS``;
``parse_stats(text)`` returns named drop counters. Nothing is guessed: anything
the contract does not cover is dropped and counted.
"""
from __future__ import annotations

import html
import re
from collections import Counter
from datetime import datetime

from .legacy_issueno import KEYS

_EVENT = re.compile(
    r"<(?P<close>/?)table\b[^>]*>"
    r"|<tr\b[^>]*>(?P<tr>.*?)</tr\s*>"
    r"|<(?P<tag>div|p)\b[^>]*>(?P<leaf>(?:(?!<(?:div|p|table)\b).)*?)</(?P=tag)\s*>",
    re.I | re.S)
_FURNITURE = re.compile(r"^(?:Page \| \d+|Page \d+|\d+)$")
_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)(?:</t[dh]\s*>|(?=<t[dh]\b)|$)", re.I | re.S)
_BR = re.compile(r"<br\s*/?>", re.I)
_TAG = re.compile(r"<[^>]*>")
_WS = re.compile(r"\s+")
_ID = re.compile(r"^\d+(?:\.\d+)*(?:\.?[A-Za-z])?\.?$")
_ROMAN = re.compile(r"^(?:XXX|XX?(?:IX|IV|V?I{0,3})|IX|IV|V?I{1,3}|V)$", re.I)
_SECTION = re.compile(r"^(?:AGM|EGM)(?=.)")
_GLUED = re.compile(r"^\d[\d.]*[A-Za-z]")
_LETTER_DOT_DIGITS = re.compile(r"^[A-Za-z]{1,2}\.\d[\d.]*$")
_DATE = re.compile(r"^(\d{1,2})-([A-Za-z]{3})-(\d{2})$")

HEADER = ("Proposal", "Proposed by", "Mgt. Position", "Registrant Voted")
_VOTES = {"Voted - " + v for v in ("For", "Against", "Abstain", "Withheld", "Withhold", "Split",
                                   "1 Year", "One Year", "2 Years", "3 Years", "Three Years")}
_VOTES |= {"Did Not Vote", "Do Not Vote", "Take No Action", "Non-Voting"}
_RECS = {"For", "Against", "Abstain", "Withhold", "None", "N/A", "1 Year", "One Year",
         "2 Years", "3 Years", "Three Years", "Undetermined", "Non-Voting"}
_PROPONENTS = {"Management", "Issuer", "Shareholder", "N/A", "Non-Voting"}
_COLUMN_VALUES = _VOTES | _RECS | _PROPONENTS


def _cell_value(raw: str) -> str:
    s = _TAG.sub("", _BR.sub(" ", raw))
    return _WS.sub(" ", html.unescape(s).replace("\xa0", " ")).strip()


def _read_rows(text: str, stats: Counter) -> list[list[str]]:
    """HR1: one stream of non-ignored rows (table rows, plus leaf div/p outside tables)."""
    out: list[list[str]] = []
    depth = 0
    for m in _EVENT.finditer(text):
        if m.group("tr") is not None:
            vals = [v for v in (_cell_value(c) for c in _CELL.findall(m.group("tr"))) if v]
        elif m.group("leaf") is not None:
            if depth > 0:
                continue
            v = _cell_value(m.group("leaf"))
            vals = [v] if v else []
        else:
            depth = max(0, depth + (-1 if m.group("close") else 1))
            continue
        if not vals:
            continue
        if len(vals) == 1 and _FURNITURE.match(vals[0]):
            stats["page_furniture"] += 1
            continue
        out.append(vals)
    return out


def _is_column_row(vals: list[str]) -> bool:
    return (len(vals) >= 3 and vals[-1] in _VOTES and vals[-2] in _RECS
            and vals[-3] in _PROPONENTS)


def _after(value: str, label: str) -> str | None:
    """Text after `label` in value, or None if absent."""
    i = value.find(label)
    return None if i < 0 else value[i + len(label):].strip()


def _label_value(vals: list[str], label: str, stop: str | None = None) -> str:
    """Text after label in the first value, else in the second; cut at `stop`."""
    for v in vals[:2]:
        t = _after(v, label)
        if t is not None:
            if stop and stop in t:
                t = t.split(stop, 1)[0].strip()
            return t
    return ""


def _bad_id_token(piece: str) -> bool:
    """HR8: does the text start with an id-like token H6(a) does not accept?"""
    toks = piece.split()
    if not toks:
        return False
    tok = toks[0]
    if tok in ("AGM", "EGM") and len(toks) > 1:
        tok = toks[1]
    tok = _SECTION.sub("", tok)
    if _ID.match(tok):
        return False
    if tok[-1] in ".)":
        body = tok.rstrip(".)")
        if body and (_ROMAN.match(body) or (body.isalpha() and len(body) <= 2)
                     or (re.fullmatch(r"[A-Za-z0-9.]+", body) and any(c.isdigit() for c in body))):
            return True
    return bool(_GLUED.match(tok) or _LETTER_DOT_DIGITS.match(tok))


def _parse_date(s: str) -> str | None:
    m = _DATE.match(s)
    if not m:
        return None
    try:
        d = datetime.strptime(f"{m.group(1)}-{m.group(2).title()}-{m.group(3)}", "%d-%b-%y")
    except ValueError:
        return None
    return f"{d.month:02d}/{d.day:02d}/20{m.group(3)}"


def _run(text: str) -> tuple[list[dict], Counter]:
    stats: Counter = Counter()
    rows = _read_rows(text, stats)
    out: list[dict] = []

    # H2: heading of every column header row, precomputed; a bad one rejects the doc.
    headings: dict[int, str] = {}
    for i, vals in enumerate(rows):
        if tuple(vals) == HEADER:
            if i == 0 or len(rows[i - 1]) != 1:
                stats["doc_rejected"] += 1
                return [], stats
            headings[i] = rows[i - 1][0]

    fund: str | None = None
    ident: tuple[str, str, str] | None = None   # identity a bare Meeting Date may inherit
    new_ident: tuple[str, str, str] | None = None
    pend_issuer: str | None = None
    meeting: dict | None = None
    skip = False                                # HR6: skipping a page-split proposal's tail
    prev_kind = "other"                         # 'secid' | 'close' | 'header' | 'other'

    def drop_open(m: dict) -> None:
        if m["open"] is not None:
            stats["drop_proposal_unclosed"] += 1
            m["open"] = None

    def finalize(m: dict) -> bool:
        """Close a meeting; emit its rows unless it is dead or a proxy contest."""
        drop_open(m)
        if m["dead"]:
            return False
        props = m["props"]
        texts = [p["proposal_text"] for p in props]
        ids = [p["proposal_id"] for p in props if p["proposal_id"]]
        low = " ".join(texts).lower()
        if ("contest" in m["meeting_type"].lower() or len(ids) != len(set(ids))
                or "dissident" in low or "management nominee" in low
                or len(texts) != len(set(texts))):
            stats["drop_meeting_contest"] += 1
            return False
        out.extend(props)
        stats["meetings"] += 1
        return True

    def kill(reason: str) -> None:
        nonlocal ident
        meeting["dead"] = True
        ident = None
        stats[reason] += 1

    for i, vals in enumerate(rows):
        kind = "other"
        first = vals[0]

        if skip and i not in headings:
            nxt_sec = len(vals) == 1 and i + 1 < len(rows) and rows[i + 1][0].startswith("Security ID:")
            if (nxt_sec or first.startswith("Meeting Date:")
                    or (len(vals) >= 2 and _ID.match(first) and vals[1] not in _COLUMN_VALUES)):
                skip = False

        if i in headings:
            pend_issuer = None
            skip = False
            if headings[i] == fund:
                kind = "header"
                if meeting is not None and not meeting["dead"] and meeting["open"] is not None:
                    skip = True
                if meeting is not None:
                    drop_open(meeting)
            else:
                if meeting is not None:
                    finalize(meeting)
                meeting, ident, new_ident = None, None, None
                fund = headings[i]
        elif len(vals) == 1 and i + 1 in headings:
            continue                                # the repeated fund-heading row itself
        elif fund is None:
            stats["row_before_header"] += 1
        elif skip:
            stats["row_skipped_page_split"] += 1
            if _is_column_row(vals):
                skip = False
        elif (len(vals) == 1 and i + 1 < len(rows)
              and rows[i + 1][0].startswith("Security ID:")):
            if meeting is not None:
                finalize(meeting)
            meeting, ident, new_ident = None, None, None
            pend_issuer = first
        elif first.startswith("Security ID:"):
            if pend_issuer is None:
                stats["secid_without_issuer"] += 1
                if meeting is not None:
                    kill("drop_meeting_unplaceable_row")
                ident = None
            else:
                sid = first[len("Security ID:"):]
                tick = ""
                if "Ticker:" in sid:
                    sid, tick = sid.split("Ticker:", 1)
                else:
                    tick = _label_value(vals[1:2], "Ticker:")
                new_ident = (pend_issuer, sid.strip(), tick.strip())
                pend_issuer = None
                kind = "secid"
        elif (len(vals) == 1 and prev_kind == "secid" and new_ident is not None
              and first.startswith("Ticker:")):
            new_ident = (new_ident[0], new_ident[1], first[len("Ticker:"):].strip())
            kind = "secid"
        elif (len(vals) == 1 and prev_kind == "date" and meeting is not None
              and not meeting["dead"] and first.startswith("Meeting Type:")):
            meeting["meeting_type"] = first[len("Meeting Type:"):].strip()
            kind = "date"
        elif first.startswith("Meeting Date:"):
            pend_issuer = None
            ok = True
            if meeting is not None:
                ok = finalize(meeting)
                meeting = None
            if prev_kind == "secid":
                base = new_ident
            elif ident is not None and ok and prev_kind in ("close", "header"):
                base = ident
            else:
                base = None
                stats["drop_meeting_bare_date"] += 1
            new_ident = None
            ident = None
            if base is not None:
                date = _parse_date(_label_value(vals, "Meeting Date:", "Meeting Type:"))
                if date is None:
                    stats["drop_meeting_bad_date"] += 1
                else:
                    ident = base
                    meeting = {"dead": False, "open": None, "props": [], "pids": set(),
                               "meeting_type": _label_value(vals, "Meeting Type:"),
                               "date": date}
                    kind = "date"
        elif meeting is None:
            stats["row_outside_meeting"] += 1
        elif meeting["dead"]:
            stats["row_in_dropped_meeting"] += 1
        else:
            is_col = _is_column_row(vals)
            if not is_col and vals[-1].startswith("Voted"):
                kill("drop_meeting_voted_not_column")
                prev_kind = kind
                continue
            starts = (len(vals) >= 2 and _ID.match(first) is not None
                      and vals[1] not in _COLUMN_VALUES)
            if starts:
                drop_open(meeting)
                meeting["open"] = {"id": first.rstrip("."), "text": []}
                pieces = vals[1:-3] if is_col else vals[1:]
            else:
                pieces = vals[:-3] if is_col else vals
                if meeting["open"] is None:
                    if not pieces:
                        kill("drop_meeting_unplaceable_row")
                        pieces = None
                    else:
                        meeting["open"] = {"id": "", "text": []}
            if not meeting["dead"]:
                cur = meeting["open"]
                if not cur["text"] and pieces and _bad_id_token(pieces[0]):
                    kill("drop_meeting_bad_id_token")
            if not meeting["dead"]:
                cur["text"].extend(pieces)
                if is_col:
                    text = _WS.sub(" ", " ".join(cur["text"])).strip()
                    meeting["open"] = None
                    kind = "close"
                    if not text:
                        stats["drop_proposal_empty_text"] += 1
                    else:
                        v = vals[-1]
                        v = v[len("Voted - "):] if v.startswith("Voted - ") else v
                        iss, sid, tick = ident
                        meeting["props"].append({
                            "fund_heading": fund, "issuer_name": iss, "ticker": tick,
                            "security_id": sid, "meeting_date": meeting["date"],
                            "meeting_status": "", "meeting_type": meeting["meeting_type"],
                            "country": "", "proposal_id": cur["id"], "proposal_text": text,
                            "proponent": vals[-3], "rec": vals[-2], "vote": v,
                            "for_against": ""})
        prev_kind = kind

    if meeting is not None:
        finalize(meeting)
    stats["rows"] = len(out)
    assert all(tuple(r) == KEYS for r in out)
    return out, stats


def parse(text: str) -> list[dict]:
    return _run(text)[0]


def parse_stats(text: str) -> Counter:
    return _run(text)[1]
