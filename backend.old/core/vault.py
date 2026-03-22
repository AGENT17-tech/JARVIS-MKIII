"""
JARVIS-MKIII — vault.py
AES-256-GCM encrypted secrets store.
Keys never touch plaintext files or environment variables after initial setup.

Usage:
    python vault.py init                   # create vault, set master password
    python vault.py set ANTHROPIC_API_KEY  # store a secret
    python vault.py get ANTHROPIC_API_KEY  # retrieve a secret (for scripts)

From code:
    from core.vault import Vault
    vault = Vault()
    api_key = vault.get("ANTHROPIC_API_KEY")
"""

import os
import json
import base64
import getpass
import argparse
import struct
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.backends import default_backend

VAULT_PATH = Path(__file__).parent.parent / "config" / ".vault"
SALT_SIZE = 32
NONCE_SIZE = 12
KEY_SIZE = 32  # 256-bit


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=KEY_SIZE, n=2**17, r=8, p=1,
                 backend=default_backend())
    return kdf.derive(password.encode())


class Vault:
    def __init__(self, vault_path: Path = VAULT_PATH):
        self._path = vault_path
        self._cache: dict | None = None
        self._key: bytes | None = None

    def _load_raw(self) -> tuple[bytes, bytes, bytes]:
        """Returns (salt, nonce, ciphertext)."""
        if not self._path.exists():
            raise FileNotFoundError(
                "Vault not initialised. Run: python vault.py init"
            )
        data = self._path.read_bytes()
        salt = data[:SALT_SIZE]
        nonce = data[SALT_SIZE:SALT_SIZE + NONCE_SIZE]
        ct = data[SALT_SIZE + NONCE_SIZE:]
        return salt, nonce, ct

    def _unlock(self, password: str | None = None) -> None:
        if self._key is not None:
            return
        salt, nonce, ct = self._load_raw()
        pwd = password or getpass.getpass("Vault password: ")
        key = _derive_key(pwd, salt)
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ct, None)
        self._cache = json.loads(plaintext.decode())
        self._key = key
        self._salt = salt

    def _save(self) -> None:
        assert self._key and self._cache is not None
        nonce = os.urandom(NONCE_SIZE)
        aesgcm = AESGCM(self._key)
        ct = aesgcm.encrypt(nonce, json.dumps(self._cache).encode(), None)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(self._salt + nonce + ct)

    # ── Public API ──────────────────────────────────────────────────────────

    def get(self, key: str, password: str | None = None) -> str:
        self._unlock(password)
        if key not in self._cache:
            raise KeyError(f"Secret '{key}' not found in vault.")
        return self._cache[key]

    def set(self, key: str, value: str, password: str | None = None) -> None:
        self._unlock(password)
        self._cache[key] = value
        self._save()

    def delete(self, key: str, password: str | None = None) -> None:
        self._unlock(password)
        self._cache.pop(key, None)
        self._save()

    def list_keys(self, password: str | None = None) -> list[str]:
        self._unlock(password)
        return list(self._cache.keys())


# ── CLI ─────────────────────────────────────────────────────────────────────

def _cmd_init(args):
    if VAULT_PATH.exists():
        print("Vault already exists. Delete config/.vault to reinitialise.")
        return
    pwd = getpass.getpass("Set master password: ")
    confirm = getpass.getpass("Confirm: ")
    if pwd != confirm:
        print("Passwords do not match.")
        return
    salt = os.urandom(SALT_SIZE)
    key = _derive_key(pwd, salt)
    nonce = os.urandom(NONCE_SIZE)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, json.dumps({}).encode(), None)
    VAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    VAULT_PATH.write_bytes(salt + nonce + ct)
    print("Vault initialised.")


def _cmd_set(args):
    value = getpass.getpass(f"Value for '{args.key}': ")
    v = Vault()
    v.set(args.key, value)
    print(f"Stored '{args.key}'.")


def _cmd_get(args):
    v = Vault()
    print(v.get(args.key))


def _cmd_list(args):
    v = Vault()
    keys = v.list_keys()
    print("\n".join(keys) if keys else "(vault is empty)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JARVIS-MKIII Secret Vault")
    sub = parser.add_subparsers()

    p_init = sub.add_parser("init");  p_init.set_defaults(func=_cmd_init)
    p_set  = sub.add_parser("set");   p_set.add_argument("key");  p_set.set_defaults(func=_cmd_set)
    p_get  = sub.add_parser("get");   p_get.add_argument("key");  p_get.set_defaults(func=_cmd_get)
    p_list = sub.add_parser("list");  p_list.set_defaults(func=_cmd_list)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
