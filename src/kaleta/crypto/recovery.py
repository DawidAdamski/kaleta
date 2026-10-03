# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recovery codes: a second way to unwrap a member's private key.

26 Crockford-base32 characters — 130 bits, shown once at sign-up as five
groups. The code goes through the same Argon2id as a passphrase
(``derive_kek``) and wraps the same private key a second time, so it can stand
in for a forgotten passphrase and for nothing else: it opens the private key,
the member then chooses a new passphrase, and the key is wrapped again.
"""

from __future__ import annotations

import secrets

RECOVERY_CODE_LENGTH = 26
#: Crockford base32: no I, L, O or U, so a hand-copied code reads back.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_GROUP = 5
#: What people write for the letters Crockford leaves out.
_LOOKALIKES = str.maketrans({"O": "0", "I": "1", "L": "1"})


def new_recovery_code() -> str:
    """A fresh code, grouped for reading: ``ABCDE-FGHJK-…``."""
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH))
    return "-".join(raw[i : i + _GROUP] for i in range(0, RECOVERY_CODE_LENGTH, _GROUP))


def normalise_recovery_code(code: str) -> str:
    """The canonical form a code is derived from: no spaces or dashes, upper case.

    Look-alike letters are read as the digits Crockford means by them, so a
    code copied by hand off paper still works.
    """
    cleaned = "".join(ch for ch in code.upper() if ch.isascii() and ch.isalnum())
    return cleaned.translate(_LOOKALIKES)
