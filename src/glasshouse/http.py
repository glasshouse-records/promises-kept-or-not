"""HTTP layer: rate-limited, retrying, SEC-fair-access-compliant session.

SEC requires a descriptive User-Agent with a contact address and caps
automated traffic at 10 req/s. We stay well under it. The contact email is
read from GLASSHOUSE_CONTACT so forks identify themselves, not us.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("GLASSHOUSE_DATA_DIR", "data"))
CACHE_DIR = DATA_DIR / "cache"

_CONTACT = os.environ.get("GLASSHOUSE_CONTACT", "glasshouse-watchdog@example.org")
USER_AGENT = f"Glasshouse/0.1 (public-interest research; {_CONTACT})"

_RATE_LIMIT_DELAY = 0.15  # seconds between requests (SEC cap is 10 req/s)
_last_request_ts = 0.0


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})
    retry = Retry(
        total=5,
        status_forcelist=[429, 500, 502, 503, 504],
        backoff_factor=2,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_session = build_session()


def _throttle() -> None:
    global _last_request_ts
    wait = _RATE_LIMIT_DELAY - (time.monotonic() - _last_request_ts)
    if wait > 0:
        time.sleep(wait)
    _last_request_ts = time.monotonic()


def get(url: str, params: dict | None = None, timeout: int = 30) -> requests.Response:
    _throttle()
    resp = _session.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp


def get_json(url: str, params: dict | None = None, timeout: int = 30):
    return get(url, params=params, timeout=timeout).json()


def download(url: str, dest: Path, timeout: int = 120) -> Path:
    """Stream a (possibly very large) file to dest. Returns dest.

    Skips the download if dest already exists and is non-empty — EDGAR
    filings are immutable, so a completed download never needs refreshing.
    """
    if dest.exists() and dest.stat().st_size > 0:
        logger.debug("cache hit: %s", dest)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    _throttle()
    tmp = dest.with_suffix(dest.suffix + ".part")
    with _session.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
    tmp.rename(dest)
    logger.info("downloaded %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
    return dest
