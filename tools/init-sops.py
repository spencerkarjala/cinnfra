#!/usr/bin/env python3
"""
Initialize SOPS Age keys.

Usage:
  - Generate a new Age key pair and install it for SOPS:
      python3 tools/init-sops.py --generate

  - Use an existing Age private key (will prompt) and install it for SOPS:
      python3 tools/init-sops.py

This writes the key material to:
  ${XDG_CONFIG_HOME:-$HOME/.config}/sops/age/keys.txt

Dependencies:
  - age-keygen (from the age project) must be installed and on PATH.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import shutil
import sys
import tempfile
from pathlib import Path
from subprocess import CalledProcessError, run


def _config_base_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".config"


def _keys_txt_path() -> Path:
    return _config_base_dir() / "sops" / "age" / "keys.txt"


def _require_age_keygen() -> None:
    if shutil.which("age-keygen") is None:
        print(
            "Error: 'age-keygen' is required but was not found on PATH.\n"
            "Install age (https://github.com/FiloSottile/age) and ensure 'age-keygen' is available.",
            file=sys.stderr,
        )
        sys.exit(127)


def _atomic_write(path: Path, data: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Tighten directory perms if possible (best effort)
    for d in [path.parent, path.parent.parent]:
        if d and d.exists():
            try:
                os.chmod(d, 0o700)
            except PermissionError:
                pass

    with tempfile.NamedTemporaryFile("w", dir=str(path.parent), delete=False) as tf:
        tmp_name = tf.name
        tf.write(data)
        tf.flush()
        os.fsync(tf.fileno())
    os.replace(tmp_name, path)
    try:
        os.chmod(path, mode)
    except PermissionError:
        pass


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _extract_secret_key_line(text: str) -> str | None:
    line = text.strip()
    if line.startswith("AGE-SECRET-KEY-"):
        return line
    for l in text.splitlines():
        s = l.strip()
        if s.startswith("AGE-SECRET-KEY-"):
            return s
    return None


def _derive_public_key_from_secret(secret_key_line: str) -> str:
    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        tf.write(secret_key_line.strip() + "\n")
        tmp_path = tf.name
    try:
        cp = run(["age-keygen", "-y", tmp_path], check=True, capture_output=True, text=True)
        pub = cp.stdout.strip()
        if not pub.startswith("age1"):
            raise RuntimeError("Failed to derive a valid age public key.")
        return pub
    except CalledProcessError as e:
        raise RuntimeError(
            f"age-keygen -y failed with exit code {e.returncode}: {e.stderr}"
        ) from e
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _generate_key_block_with_age_keygen() -> tuple[str, str]:
    """
    Returns (block_text, public_key).
    block_text contains the lines to be appended to keys.txt for this key.
    """
    # age-keygen -o expects the file to NOT exist yet. Use a temp directory
    # and point it at a fresh path to avoid "file exists" errors.
    with tempfile.TemporaryDirectory() as td:
        tmp_path = str(Path(td) / "age-key.txt")
        try:
            # Generate new key file
            run(["age-keygen", "-o", tmp_path], check=True, capture_output=True, text=True)
            content = Path(tmp_path).read_text(encoding="utf-8")
            # Derive public key to report back (and validate content)
            cp = run(["age-keygen", "-y", tmp_path], check=True, capture_output=True, text=True)
            public_key = cp.stdout.strip()
            block = content.rstrip() + "\n"
            return block, public_key
        except CalledProcessError as e:
            raise RuntimeError(
                f"age-keygen failed with exit code {e.returncode}: {e.stderr}"
            ) from e


def _compose_block_from_secret(secret_key_line: str, public_key: str) -> str:
    created = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"# created: {created}",
        f"# public key: {public_key}",
        secret_key_line.strip(),
        "",
    ]
    return "\n".join(lines)


def _append_key_block(keys_path: Path, block: str, secret_key_line: str) -> None:
    existing = _read_text(keys_path)
    if existing and secret_key_line in existing:
        print(f"Key already present in {keys_path}. No changes made.", file=sys.stderr)
        return
    new_content = existing
    if new_content and not new_content.endswith("\n"):
        new_content += "\n"
    if new_content:
        # Separate multiple keys with a blank line
        if not new_content.endswith("\n\n"):
            new_content += "\n"
    new_content += block
    _atomic_write(keys_path, new_content, mode=0o600)


def _ensure_sops_config(public_key: str) -> Path:
    """
    Ensure a minimal .sops.yaml exists in the current working directory,
    configured to use the provided Age public key for files under kubernetes/secrets/.
    If the file already exists, it will not be modified.
    Returns the Path to the config file.
    """
    cfg_path = Path.cwd() / ".sops.yaml"
    if cfg_path.exists():
        return cfg_path
    content = (
        "# Managed by tools/init-sops.py\n"
        "# Uses Age public key to encrypt files matched by creation_rules.\n"
        "creation_rules:\n"
        "  - path_regex: kubernetes/secrets/.*\\.(ya?ml)$\n"
        "    age:\n"
        f"      - {public_key}\n"
    )
    _atomic_write(cfg_path, content, mode=0o644)
    return cfg_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialize SOPS Age keys in ${XDG_CONFIG_HOME:-$HOME/.config}/sops/age/keys.txt"
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate a new Age key pair and install it (default is to prompt for an existing private key).",
    )
    args = parser.parse_args(argv)

    _require_age_keygen()
    keys_path = _keys_txt_path()

    print(f"Using keys_path: {keys_path}")

    if args.generate:
        try:
            block, public_key = _generate_key_block_with_age_keygen()
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        # Extract secret key line for duplication check
        secret_line = _extract_secret_key_line(block)
        if not secret_line:
            print("Error: Could not parse generated secret key.", file=sys.stderr)
            return 1
        _append_key_block(keys_path, block, secret_line)
        print(f"Age public key: {public_key}")
        print(f"Installed key to: {keys_path}")
        cfg_path = _ensure_sops_config(public_key)
        print(f"SOPS config: {cfg_path}")
        return 0

    # Prompt for existing private key
    print(
        "Enter your Age private key (the single line starting with 'AGE-SECRET-KEY-').\n"
        "Input is hidden; paste and press Enter.",
        file=sys.stderr,
    )
    try:
        import getpass

        secret = getpass.getpass("> ").strip()
    except Exception:
        # Fallback input (visible) only if getpass fails (rare TTY cases)
        print("Warning: Unable to disable echo. Your input will be visible.", file=sys.stderr)
        secret = input("> ").strip()

    secret_line = _extract_secret_key_line(secret)
    if not secret_line:
        print("Error: Did not detect a valid 'AGE-SECRET-KEY-' line.", file=sys.stderr)
        return 2

    try:
        public_key = _derive_public_key_from_secret(secret_line)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 3

    block = _compose_block_from_secret(secret_line, public_key)
    _append_key_block(keys_path, block, secret_line)
    print(f"Age public key: {public_key}")
    print(f"Installed key to: {keys_path}")
    cfg_path = _ensure_sops_config(public_key)
    print(f"SOPS config: {cfg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
