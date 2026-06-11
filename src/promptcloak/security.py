from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_FILE_MODE = 0o600


def generate_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def load_key(key_file: Path) -> bytes:
    env_key = os.getenv("PROMPTCLOAK_CONFIG_KEY")
    raw = env_key or key_file.read_text(encoding="utf-8").strip()
    return base64.urlsafe_b64decode(raw)


def write_key_file(key_file: Path) -> str:
    key = generate_key()
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(key + "\n", encoding="utf-8")
    key_file.chmod(KEY_FILE_MODE)
    return key


def encrypt_text(plaintext: str, key: bytes) -> str:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_text(ciphertext: str, key: bytes) -> str:
    payload = base64.urlsafe_b64decode(ciphertext)
    nonce, encrypted = payload[:12], payload[12:]
    return AESGCM(key).decrypt(nonce, encrypted, None).decode("utf-8")
