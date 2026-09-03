from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

# HMAC-SHA256, not a plain hash: a plain sha256 written to a sibling file
# only catches accidental corruption -- an attacker with enough filesystem
# access to replace model.pkl (the arbitrary-code-execution vector
# pickle.load opens up) can just as easily overwrite a sibling .sha256 file
# to match their replacement. Keying the MAC with a secret that lives in
# Settings/the environment, not on disk next to the model, means forging a
# valid signature requires the key too.


def _signature_path(model_path: Path) -> Path:
    return model_path.with_name(model_path.name + ".sig")


def sign(model_path: Path, key: str) -> str:
    return hmac.new(key.encode("utf-8"), model_path.read_bytes(), hashlib.sha256).hexdigest()


def write_signature(model_path: Path, key: str) -> None:
    _signature_path(model_path).write_text(sign(model_path, key))


def remove_signature(model_path: Path) -> None:
    _signature_path(model_path).unlink(missing_ok=True)


def verify(model_path: Path, key: str) -> bool:
    sig_path = _signature_path(model_path)
    if not sig_path.exists():
        return False
    expected = sig_path.read_text().strip()
    return hmac.compare_digest(expected, sign(model_path, key))
