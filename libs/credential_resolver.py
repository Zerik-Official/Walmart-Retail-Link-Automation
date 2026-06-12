"""Resolves Walmart credentials from either .env or LastPass vault."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from libs.lastpass_patch import LastPassClient
from utils.logger import log, Tags


@dataclass
class ResolvedCredentials:
    """Final credentials ready to use for Walmart login."""

    username: str = field(default="")
    password: str = field(default="")


def resolve_credentials(
    use_lastpass: bool,
    walmart_username: str,
    walmart_password: str,
    lastpass_email: str,
    lastpass_password: str,
) -> ResolvedCredentials:
    """Return the credentials to use.

    * If *use_lastpass* is ``True``:
        - Connects to LastPass, shows available accounts,
          lets the user pick one, returns its username/password.

    * Otherwise returns the direct *walmart_username* / *walmart_password*.
    """
    if not use_lastpass:
        return ResolvedCredentials(username=walmart_username, password=walmart_password)

    # --- Connect to LastPass ---
    log("INFO", Tags.LASTPASS, "Connecting to vault ...")
    try:
        lp = LastPassClient(lastpass_email, lastpass_password)
    except Exception as exc:
        log("CRITICAL", Tags.LASTPASS, f"Failed to connect: {exc}")
        sys.exit(1)

    accounts = lp.accounts
    if not accounts:
        log("CRITICAL", Tags.LASTPASS, "No accounts found in vault.")
        sys.exit(1)

    # --- Show accounts and let user pick ---
    log("INFO", Tags.LASTPASS, f"Found {len(accounts)} account(s)")
    for i, acct in enumerate(accounts, 1):
        url_display = acct.url or "(no url)"
        print(f"    {i:>3}. {acct.name:40s} {acct.username:30s} {url_display}")

    while True:
        raw = input(f"  Choose account [1-{len(accounts)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(accounts):
            chosen = accounts[int(raw) - 1]
            break
        print(f"  Please enter a number between 1 and {len(accounts)}.")

    log("INFO", Tags.LASTPASS, f"Using: {chosen.name} ({chosen.username})")
    return ResolvedCredentials(
        username=chosen.username or "",
        password=chosen.password or "",
    )
