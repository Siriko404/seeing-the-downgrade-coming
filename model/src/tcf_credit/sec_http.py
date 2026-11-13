"""Helper for the SEC downloads (steps 1 and 3b): HTTP access to SEC EDGAR with the contact the SEC asks every
automated client to declare.

Goes in:  the web address to fetch. Comes out: the downloaded data. Data: public SEC data (network needed).

The SEC asks every automated client to declare a contact, so each request carries one (for example your name and
e-mail). Use your own.
The contact is read from the environment variable TCF_SEC_CONTACT or from
~/.config/tcf_credit/settings.toml ([sec] contact). It is never stored in this repository.
SEC fair access: at most 10 requests per second; this module waits 0.15 s between requests.
"""
import os
import time
import tomllib
import urllib.request
from pathlib import Path

SETTINGS = Path.home() / ".config/tcf_credit/settings.toml"
_last = [0.0]


def contact() -> str:
    """The declared contact, or stop with a message saying how to set it."""
    value = os.environ.get("TCF_SEC_CONTACT", "").strip()
    if not value and SETTINGS.is_file():
        value = str(tomllib.load(SETTINGS.open("rb")).get("sec", {}).get("contact", "")).strip()
    if not value:
        raise SystemExit("Set TCF_SEC_CONTACT or [sec] contact in ~/.config/tcf_credit/settings.toml")
    return value


def request(url: str, method: str = "GET") -> urllib.request.Request:
    """A request carrying the declared contact in its User-Agent header."""
    return urllib.request.Request(url, method=method, headers={"User-Agent": f"tcf-credit-lecture {contact()}",
                                                              "Accept-Encoding": "identity"})


def open_url(url: str, method: str = "GET", timeout: int = 120):
    """Open a URL after waiting 0.15 s so that requests stay at most about 6.7 per second."""
    wait = 0.15 - (time.monotonic() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.monotonic()
    return urllib.request.urlopen(request(url, method), timeout=timeout)


def download(url: str, dest: Path, chunk: int = 1 << 20) -> Path:
    """Download to dest (via dest.part), skipping if dest exists."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    part = dest.with_suffix(dest.suffix + ".part")
    with open_url(url, timeout=600) as r, part.open("wb") as fh:
        while True:
            b = r.read(chunk)
            if not b:
                break
            fh.write(b)
    part.rename(dest)
    return dest
