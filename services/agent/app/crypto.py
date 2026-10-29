from cryptography.fernet import Fernet


def encrypt(plaintext: str, key: str) -> str:
    return Fernet(key.encode()).encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str, key: str) -> str:
    return Fernet(key.encode()).decrypt(ciphertext.encode()).decode()


def key_hint(api_key: str) -> str:
    """Last four characters, safe to show back to the user."""
    return api_key[-4:]
