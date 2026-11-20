"""Backend-only credentials for live generation profiles."""

import os
import stat
from pathlib import Path
from tempfile import NamedTemporaryFile

from cryptography.fernet import Fernet, InvalidToken
from psycopg import Connection
from psycopg.rows import dict_row

from app.core.config import Settings
from app.db.connection import get_connection


def credential_cipher(path: Path, *, create: bool = False) -> Fernet:
    try:
        if create:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            directory = path.parent.lstat()
            if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid() or directory.st_mode & 0o077:
                raise PermissionError
            if not path.exists():
                # Publish a complete key atomically. Concurrent workers keep the winner.
                with NamedTemporaryFile(dir=path.parent) as draft:
                    draft.write(Fernet.generate_key())
                    draft.flush()
                    os.fsync(draft.fileno())
                    try:
                        os.link(draft.name, path)
                    except FileExistsError:
                        pass
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise PermissionError
            return Fernet(stream.read(45))
    except (OSError, ValueError):
        raise RuntimeError("The local provider credential key is unavailable or has unsafe permissions.") from None


def read_profile(conn: Connection, purpose: str) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(
            "SELECT * FROM generation_profiles WHERE purpose=%s", (purpose,),
        ).fetchone()


def profile_settings(defaults: Settings, profile: dict) -> Settings:
    credential = ""
    if profile["credential"]:
        try:
            credential = credential_cipher(defaults.provider_key_path).decrypt(bytes(profile["credential"])).decode()
        except (InvalidToken, UnicodeError):
            raise RuntimeError("The stored provider credential cannot be decrypted. Replace the key in Settings.") from None
    return defaults.model_copy(update={
        "generation_provider": profile["provider"],
        "generation_model": profile["model"],
        "generation_base_url": profile["endpoint"],
        "generation_api_key": credential,
        "gemini_model": profile["model"],
        "gemini_api_key": credential,
        "ollama_context_tokens": profile.get("ollama_context_tokens"),
    })


def active_settings(defaults: Settings, purpose: str) -> Settings:
    with get_connection() as conn:
        profile = read_profile(conn, purpose)
        if profile is None and purpose == "extraction":
            profile = read_profile(conn, "answer")
    return profile_settings(defaults, profile) if profile else defaults
