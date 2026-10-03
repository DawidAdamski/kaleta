# SPDX-License-Identifier: AGPL-3.0-or-later
"""The key hierarchy: wrap, seal, recover, and the key ring that holds the result.

Covers: KAL-ENC-002, KAL-ENC-004, KAL-ENC-005, KAL-ENC-006, KAL-ENC-007
"""

from __future__ import annotations

import json

import pytest

from kaleta.crypto import (
    DataKey,
    KdfParams,
    KeyRing,
    create_key_material,
    derive_index_key,
    derive_kek,
    generate_dek,
    generate_member_keys,
    new_recovery_code,
    normalise_recovery_code,
    open_data_key,
    open_private_key,
    open_sealed,
    open_with_recovery,
    seal,
    unwrap_private_key,
    with_passphrase,
    with_recovery_code,
    wrap_private_key,
)
from kaleta.crypto.keys import new_salt
from kaleta.exceptions import EncryptionError

#: Cheap enough for a unit test; the production default is asserted separately.
FAST = KdfParams(time_cost=1, memory_kib=8 * 1024, parallelism=1)
PASSPHRASE = "correct horse battery staple"


def test_a_wrapped_private_key_opens_with_its_passphrase_only() -> None:
    keys = generate_member_keys()
    salt = new_salt()
    wrapped = wrap_private_key(keys.private_key, derive_kek(PASSPHRASE, salt, FAST))

    assert unwrap_private_key(wrapped, derive_kek(PASSPHRASE, salt, FAST)) == keys.private_key
    with pytest.raises(EncryptionError):
        unwrap_private_key(wrapped, derive_kek("not the passphrase", salt, FAST))
    assert keys.private_key not in wrapped


def test_a_sealed_data_key_opens_for_its_member_and_not_for_another() -> None:
    ania, bartek = generate_member_keys(), generate_member_keys()
    dek = generate_dek()

    sealed = seal(dek, ania.public_key)

    assert open_sealed(sealed, ania.private_key) == dek
    with pytest.raises(EncryptionError):
        open_sealed(sealed, bartek.private_key)
    # Sealing twice gives two different boxes: nothing to correlate.
    assert seal(dek, ania.public_key) != sealed


def test_a_damaged_box_is_refused() -> None:
    ania = generate_member_keys()
    sealed = bytearray(seal(generate_dek(), ania.public_key))
    sealed[-1] ^= 0x01

    with pytest.raises(EncryptionError):
        open_sealed(bytes(sealed), ania.private_key)


def test_material_round_trip_from_passphrase_to_data_key() -> None:
    dek = generate_dek()
    material, private_key = create_key_material(
        PASSPHRASE, dek=dek, recovery_code=None, params=FAST
    )

    assert open_private_key(material, PASSPHRASE) == private_key
    assert open_data_key(material, private_key, version=1).dek == dek
    with pytest.raises(EncryptionError):
        open_private_key(material, "wrong passphrase!!")


def test_the_recovery_code_opens_the_same_private_key() -> None:
    code = new_recovery_code()
    material, private_key = create_key_material(
        PASSPHRASE, dek=generate_dek(), recovery_code=code, params=FAST
    )

    assert material.has_recovery
    # As copied by hand: lower case, spaces instead of dashes.
    assert open_with_recovery(material, code.lower().replace("-", " ")) == private_key
    with pytest.raises(EncryptionError):
        open_with_recovery(material, new_recovery_code())


def test_recovery_codes_are_26_crockford_characters() -> None:
    code = new_recovery_code()
    canonical = normalise_recovery_code(code)

    assert len(canonical) == 26
    assert set(canonical) <= set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
    assert normalise_recovery_code("o1l-i") == "0111"


def test_changing_the_passphrase_leaves_recovery_and_the_data_key_alone() -> None:
    dek = generate_dek()
    code = new_recovery_code()
    material, private_key = create_key_material(
        PASSPHRASE, dek=dek, recovery_code=code, params=FAST
    )

    changed = with_passphrase(material, private_key, "a brand new passphrase")

    assert changed.recovery_wrapped == material.recovery_wrapped
    assert changed.dek_sealed == material.dek_sealed
    assert open_private_key(changed, "a brand new passphrase") == private_key
    with pytest.raises(EncryptionError):
        open_private_key(changed, PASSPHRASE)
    assert open_with_recovery(changed, code) == private_key


def test_regenerating_the_recovery_code_retires_the_old_one() -> None:
    old = new_recovery_code()
    material, private_key = create_key_material(
        PASSPHRASE, dek=generate_dek(), recovery_code=old, params=FAST
    )
    new = new_recovery_code()

    regenerated = with_recovery_code(material, private_key, new)

    assert open_with_recovery(regenerated, new) == private_key
    with pytest.raises(EncryptionError):
        open_with_recovery(regenerated, old)


def test_kdf_parameters_are_stored_and_honoured() -> None:
    assert KdfParams() == KdfParams(time_cost=3, memory_kib=65536, parallelism=1)
    material, _ = create_key_material(PASSPHRASE, dek=None, recovery_code=None, params=FAST)

    assert json.loads(material.kdf_params) == {"alg": "argon2id", "m": 8192, "p": 1, "t": 1}
    # The stored parameters, not the defaults, are what unlocks it.
    salt = material.private_key_salt
    assert derive_kek(PASSPHRASE, salt, FAST) != derive_kek(PASSPHRASE, salt, KdfParams())
    open_private_key(material, PASSPHRASE)


def test_unreadable_kdf_parameters_are_an_encryption_error() -> None:
    with pytest.raises(EncryptionError):
        KdfParams.from_json('{"alg": "scrypt", "t": 1, "m": 1, "p": 1}')
    with pytest.raises(EncryptionError):
        KdfParams.from_json(None)


def test_the_index_key_is_derived_and_differs_from_the_data_key() -> None:
    dek = generate_dek()

    assert derive_index_key(dek) == DataKey(dek).index_key
    assert derive_index_key(dek) != dek


def test_nothing_secret_is_in_a_repr() -> None:
    dek = generate_dek()
    material, private_key = create_key_material(
        PASSPHRASE, dek=dek, recovery_code=None, params=FAST
    )
    ring = KeyRing(lambda: 3600)
    entry = ring.put("s1", DataKey(dek), member_ref="local:1", private_key=private_key)

    for shown in (repr(DataKey(dek)), repr(material), repr(entry), repr(ring)):
        assert dek.hex() not in shown
        assert private_key.hex() not in shown
        assert str(dek) not in shown


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_the_ring_unlocks_and_forgets_after_its_ttl() -> None:
    dek = generate_dek()
    material, _ = create_key_material(PASSPHRASE, dek=dek, recovery_code=None, params=FAST)
    clock = _Clock()
    ring = KeyRing(lambda: 60, clock=clock)

    unlocked = ring.unlock("s1", material, PASSPHRASE, member_ref="local:1", key_version=1)

    assert unlocked.data_key.dek == dek
    assert ring.get("s1") == unlocked
    clock.now += 59
    assert ring.get("s1") is not None
    clock.now += 2
    assert ring.get("s1") is None
    assert ring.count() == 0


def test_a_wrong_passphrase_unlocks_nothing() -> None:
    material, _ = create_key_material(
        PASSPHRASE, dek=generate_dek(), recovery_code=None, params=FAST
    )
    ring = KeyRing(lambda: 60)

    with pytest.raises(EncryptionError):
        ring.unlock("s1", material, "not it at all", member_ref="local:1", key_version=1)
    assert ring.get("s1") is None


def test_lock_lock_member_and_bearer_lookup() -> None:
    ring = KeyRing(lambda: 60)
    ring.put("s1", DataKey(generate_dek()), member_ref="tenant:1:user:1")
    ring.put("s2", DataKey(generate_dek()), member_ref="tenant:1:user:1")
    ring.put("s3", DataKey(generate_dek()), member_ref="tenant:1:user:2")

    assert ring.for_member("tenant:1:user:2") is not None
    ring.lock("s3")
    assert ring.for_member("tenant:1:user:2") is None
    assert ring.lock_member("tenant:1:user:1") == 2
    assert ring.count() == 0


def test_an_unlock_survives_a_session_id_rotation() -> None:
    ring = KeyRing(lambda: 60)
    ring.put("before", DataKey(generate_dek()), member_ref="local:1")

    ring.move("before", "after")

    assert ring.get("before") is None
    assert ring.get("after") is not None


def test_a_zero_ttl_means_no_expiry() -> None:
    clock = _Clock()
    ring = KeyRing(lambda: 0, clock=clock)
    ring.put("s1", DataKey(generate_dek()), member_ref="local:1")
    clock.now += 10**9

    assert ring.get("s1") is not None


def test_a_data_key_must_be_32_bytes_with_a_one_byte_version() -> None:
    with pytest.raises(EncryptionError):
        DataKey(b"short")
    with pytest.raises(EncryptionError):
        DataKey(generate_dek(), version=256)
