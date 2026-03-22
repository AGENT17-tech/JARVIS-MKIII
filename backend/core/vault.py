"""
JARVIS-MKIII — vault.py
AES-256-GCM encrypted secrets store.

CLI:
    python vault.py init
    python vault.py set KEY
    python vault.py get KEY
    python vault.py list

Code:
    from core.vault import Vault
    key = Vault().get("GROQ_API_KEY")
"""

import os, json, base64, getpass, argparse
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.backends import default_backend

VAULT_PATH = Path(__file__).parent.parent / "config" / ".vault"
SALT_SIZE  = 32
NONCE_SIZE = 12
KEY_SIZE   = 32


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=KEY_SIZE, n=2**17, r=8, p=1, backend=default_backend())
    return kdf.derive(password.encode())


class Vault:
    def __init__(self, vault_path: Path = VAULT_PATH):
        self._path  = vault_path
        self._cache = None
        self._key   = None
        self._salt  = None
        # Auto-unlock when env var or pass file is available (never blocks service startup)
        try:
            env_pw = os.environ.get("JARVIS_VAULT_PASSWORD", "").strip()
            pass_file = Path.home() / "JARVIS_MKIII" / ".vault_pass"
            if env_pw or pass_file.exists():
                self._unlock()
        except Exception:
            pass

    @property
    def _unlocked(self) -> bool:
        return self._key is not None

    def _unlock(self, password: str = None) -> None:
        if self._key is not None:
            return
        if not self._path.exists():
            raise FileNotFoundError("Vault not initialised. Run: python vault.py init")
        data  = self._path.read_bytes()
        salt  = data[:SALT_SIZE]
        nonce = data[SALT_SIZE:SALT_SIZE + NONCE_SIZE]
        ct    = data[SALT_SIZE + NONCE_SIZE:]

        # Password resolution order (never prompt interactively in service contexts):
        #  1. Caller-supplied password argument
        #  2. JARVIS_VAULT_PASSWORD environment variable
        #  3. Password file at ~/JARVIS_MKIII/.vault_pass (chmod 600)
        #  4. Interactive getpass (CLI only — will fail inside systemd)
        if not password:
            password = os.environ.get("JARVIS_VAULT_PASSWORD", "").strip() or None
        if not password:
            pass_file = Path.home() / "JARVIS_MKIII" / ".vault_pass"
            if pass_file.exists():
                password = pass_file.read_text().strip() or None
        if not password:
            password = getpass.getpass("Vault password: ")

        key   = _derive_key(password, salt)
        self._cache = json.loads(AESGCM(key).decrypt(nonce, ct, None).decode())
        self._key   = key
        self._salt  = salt

    def _save(self) -> None:
        nonce = os.urandom(NONCE_SIZE)
        ct    = AESGCM(self._key).encrypt(nonce, json.dumps(self._cache).encode(), None)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(self._salt + nonce + ct)

    def get(self, key: str, password: str = None) -> str:
        # Check environment first — avoids interactive prompt in services
        env_val = os.environ.get(key)
        if env_val:
            return env_val
        self._unlock(password)
        if key not in self._cache:
            raise KeyError(f"Secret '{key}' not found in vault.")
        return self._cache[key]

    def set(self, key: str, value: str, password: str = None) -> None:
        self._unlock(password)
        self._cache[key] = value
        self._save()

    def list_keys(self, password: str = None) -> list:
        self._unlock(password)
        return list(self._cache.keys())


def _cmd_init(args):
    if VAULT_PATH.exists():
        print("Vault already exists."); return
    pwd = getpass.getpass("Set master password: ")
    if pwd != getpass.getpass("Confirm: "):
        print("Passwords do not match."); return
    salt = os.urandom(SALT_SIZE)
    key  = _derive_key(pwd, salt)
    nonce = os.urandom(NONCE_SIZE)
    ct    = AESGCM(key).encrypt(nonce, json.dumps({}).encode(), None)
    VAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    VAULT_PATH.write_bytes(salt + nonce + ct)
    print("Vault initialised.")

def _cmd_set(args):
    value = getpass.getpass(f"Value for '{args.key}': ")
    Vault().set(args.key, value)
    print(f"Stored '{args.key}'.")

def _cmd_get(args):
    print(Vault().get(args.key))

def _cmd_list(args):
    keys = Vault().list_keys()
    print("\n".join(keys) if keys else "(vault is empty)")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    s = p.add_subparsers()
    s.add_parser("init").set_defaults(func=_cmd_init)
    sp = s.add_parser("set"); sp.add_argument("key"); sp.set_defaults(func=_cmd_set)
    gp = s.add_parser("get"); gp.add_argument("key"); gp.set_defaults(func=_cmd_get)
    s.add_parser("list").set_defaults(func=_cmd_list)
    args = p.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        p.print_help()
