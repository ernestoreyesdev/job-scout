import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.crypto import decrypt, encrypt, key_hint


def test_round_trip():
    key = Fernet.generate_key().decode()
    ciphertext = encrypt("sk-ant-secret-value", key)

    assert ciphertext != "sk-ant-secret-value"
    assert decrypt(ciphertext, key) == "sk-ant-secret-value"


def test_wrong_key_cannot_decrypt():
    ciphertext = encrypt("sk-ant-secret-value", Fernet.generate_key().decode())

    with pytest.raises(InvalidToken):
        decrypt(ciphertext, Fernet.generate_key().decode())


def test_hint_is_last_four_characters():
    assert key_hint("sk-ant-api03-abcdWXYZ") == "WXYZ"
