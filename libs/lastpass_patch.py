"""Patched wrapper around lastpass-python (v0.3.2).

Monkey-patches outdated blob parsing (PRIK + ACCT url format)
and exposes a typed, easy-to-use interface.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 1. Apply monkey-patches to the vendored library
# ---------------------------------------------------------------------------
_PATCHED: bool = False


def _apply_patches() -> None:
    """Fix blob parsing for LastPass's current ACCT/PRIK format."""
    global _PATCHED
    if _PATCHED:
        return

    try:
        from lastpass import parser as _parser
    except ImportError:
        raise ImportError(
            "lastpass-python is not installed. Run: pip install lastpass-python"
        ) from None

    # --- PRIK chunk: new format is !base64|base64, not hex+raw AES ---
    _original_parse_prik = _parser.parse_PRIK

    def _patched_parse_prik(
        chunk: Any, encryption_key: bytes
    ) -> Any:
        return _parser.decode_aes256_cbc_base64(chunk.payload, encryption_key)

    _parser.parse_PRIK = _patched_parse_prik

    # --- ACCT chunk: URL field is now AES-CBC encrypted, not hex ---
    _original_parse_acct = _parser.parse_ACCT

    def _patched_parse_acct(chunk: Any, encryption_key: bytes) -> Any:
        from io import BytesIO

        io = BytesIO(chunk.payload)
        id_ = _parser.read_item(io)
        name = _parser.decode_aes256_plain_auto(_parser.read_item(io), encryption_key)
        group = _parser.decode_aes256_plain_auto(_parser.read_item(io), encryption_key)
        url = _parser.decode_aes256_plain_auto(_parser.read_item(io), encryption_key)  # patched
        notes = _parser.decode_aes256_plain_auto(_parser.read_item(io), encryption_key)
        _parser.skip_item(io, 2)
        username = _parser.decode_aes256_plain_auto(_parser.read_item(io), encryption_key)
        password = _parser.decode_aes256_plain_auto(_parser.read_item(io), encryption_key)
        _parser.skip_item(io, 2)
        secure_note = _parser.read_item(io)

        if secure_note == b"1":
            parsed = _parser.parse_secure_note_server(notes)
            if parsed.get("type") in _parser.ALLOWED_SECURE_NOTE_TYPES:
                url = parsed.get("url", url)
                username = parsed.get("username", username)
                password = parsed.get("password", password)

        from lastpass.account import Account
        return Account(id_, name, username, password, url, group, notes)

    _parser.parse_ACCT = _patched_parse_acct
    _PATCHED = True


# ---------------------------------------------------------------------------
# 2. Clean typed interface
# ---------------------------------------------------------------------------
@dataclass
class LastPassAccount:
    """A single credential entry from the LastPass vault."""

    id: str = field(default="")
    name: str = field(default="")
    username: str = field(default="")
    password: str = field(default="")
    url: str = field(default="")
    group: str = field(default="")
    notes: str = field(default="")


class LastPassClient:
    """Typed client that logs into LastPass and exposes vault accounts.

    Usage::

        lp = LastPassClient("email@example.com", "master-password")
        for acct in lp.accounts:
            print(acct.username, acct.password)
    """

    def __init__(self, email: str, password: str) -> None:
        _apply_patches()

        from lastpass import Vault

        self._vault = Vault.open_remote(email, password)
        self._accounts: list[LastPassAccount] = [
            LastPassAccount(
                id=a.id.decode() if isinstance(a.id, bytes) else str(a.id),
                name=a.name.decode() if isinstance(a.name, bytes) else str(a.name),
                username=a.username.decode() if isinstance(a.username, bytes) else str(a.username),
                password=a.password.decode() if isinstance(a.password, bytes) else str(a.password),
                url=a.url.decode() if isinstance(a.url, bytes) else str(a.url),
                group=a.group.decode() if isinstance(a.group, bytes) else str(a.group),
                notes=a.notes.decode() if isinstance(a.notes, bytes) else str(a.notes),
            )
            for a in self._vault.accounts
        ]

    @property
    def accounts(self) -> list[LastPassAccount]:
        """All accounts decrypted from the vault."""
        return list(self._accounts)

    def find(self, *, name: str | None = None, url: str | None = None) -> list[LastPassAccount]:
        """Search accounts by name or URL (case-insensitive substring match)."""
        results: list[LastPassAccount] = []
        for a in self._accounts:
            if name and name.lower() in a.name.lower():
                results.append(a)
            elif url and url.lower() in a.url.lower():
                results.append(a)
        return results

    def __repr__(self) -> str:
        return f"<LastPassClient accounts={len(self._accounts)}>"
