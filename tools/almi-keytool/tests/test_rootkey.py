import json

import pytest

from almi_keytool import rootkey
from almi_keytool.rootkey import KeyFileError, WrongPasswordError, create_root_key, load_root_key

PASSWORD = "correct horse battery staple"  # test-only value, not a secret  # noqa: S105


def test_root_key_uses_argon2id_t3_m256mib_and_xchacha20poly1305() -> None:
    document, key = create_root_key(PASSWORD, "root-test")

    assert document["kdf"] == {"alg": "argon2id", "opslimit": 3, "memlimit": 256 * 1024 * 1024,
                               "parallelism": 1, "salt": document["kdf"]["salt"]}
    assert document["cipher"]["alg"] == "xchacha20poly1305-ietf"
    loaded = load_root_key(json.dumps(document), PASSWORD)
    assert loaded.kid == "root-test"
    assert bytes(loaded.signing_key) == bytes(key)
    assert PASSWORD not in json.dumps(document)
    assert bytes(key).hex() not in json.dumps(document)


def test_wrong_password_and_tampering_fail_the_same_way(fast_kdf: None) -> None:
    document, _ = create_root_key(PASSWORD, "root-test")
    with pytest.raises(WrongPasswordError) as wrong:
        load_root_key(json.dumps(document), "wrong password")

    tampered = dict(document, kid="root-other")  # metadata is bound to the ciphertext
    with pytest.raises(WrongPasswordError) as changed:
        load_root_key(json.dumps(tampered), PASSWORD)

    # One message for both cases: the caller cannot tell a wrong password from a changed file.
    assert str(wrong.value) == str(changed.value) == rootkey.UNLOCK_FAILED


@pytest.mark.parametrize(
    "content",
    ["", "not json", "{}", json.dumps({"format": "almi-root-key", "version": 1})],
    ids=["empty", "not-json", "empty-object", "missing-fields"],
)
def test_corrupted_key_file_is_rejected(content: str) -> None:
    with pytest.raises(KeyFileError):
        load_root_key(content, PASSWORD)


def test_unknown_format_version_is_rejected(fast_kdf: None) -> None:
    document, _ = create_root_key(PASSWORD, "root-test")
    with pytest.raises(KeyFileError):
        load_root_key(json.dumps(dict(document, version=2)), PASSWORD)


def test_default_kdf_parameters_are_the_required_ones() -> None:
    assert (rootkey.KDF_OPSLIMIT, rootkey.KDF_MEMLIMIT) == (3, 256 * 1024 * 1024)
