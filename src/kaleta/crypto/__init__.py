# SPDX-License-Identifier: AGPL-3.0-or-later
"""User-held keys for field-level encryption (ADR-35, ``hosted-field-encryption``).

Three layers:

1. a **member keypair** (X25519) whose private key is wrapped under a KEK
   derived from the member's data passphrase (Argon2id) — and a second time
   under a recovery code;
2. a per-account **data key** (DEK), sealed to each member's public key;
3. a **blind-index key** derived from the DEK, never stored.

This package knows nothing about the database or the web: it turns bytes into
bytes. ``kaleta.db.types`` uses the DEK for columns; ``KeyService`` reads and
writes the wrapped material; the ``KeyRing`` holds unlocked keys in memory.
"""

from __future__ import annotations

from kaleta.crypto.keyring import (
    DataKey,
    KeyMaterial,
    KeyRing,
    Unlocked,
    create_key_material,
    key_ring,
    open_data_key,
    open_private_key,
    open_with_recovery,
    with_passphrase,
    with_recovery_code,
)
from kaleta.crypto.keys import (
    KdfParams,
    MemberKeys,
    derive_index_key,
    derive_kek,
    generate_dek,
    generate_member_keys,
    open_sealed,
    public_key_of,
    seal,
    unwrap_private_key,
    wrap_private_key,
)
from kaleta.crypto.recovery import new_recovery_code, normalise_recovery_code

__all__ = [
    "DataKey",
    "KdfParams",
    "KeyMaterial",
    "KeyRing",
    "MemberKeys",
    "Unlocked",
    "create_key_material",
    "derive_index_key",
    "derive_kek",
    "generate_dek",
    "generate_member_keys",
    "key_ring",
    "new_recovery_code",
    "normalise_recovery_code",
    "open_data_key",
    "open_private_key",
    "open_sealed",
    "open_with_recovery",
    "public_key_of",
    "seal",
    "unwrap_private_key",
    "with_passphrase",
    "with_recovery_code",
    "wrap_private_key",
]
