"""Merge a small deployment settings file into an existing dotenv file."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def read_updates(path: Path) -> dict[str, str]:
    updates: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        updates[key.strip()] = value.strip()
    return updates


def merge(target: Path, updates: dict[str, str]) -> None:
    lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    found: set[str] = set()
    merged: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                merged.append(f"{key}={updates[key]}")
                found.add(key)
                continue
        merged.append(line)

    if merged and merged[-1]:
        merged.append("")
    for key, value in updates.items():
        if key not in found:
            merged.append(f"{key}={value}")

    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text("\n".join(merged).rstrip() + "\n", encoding="utf-8")
    os.replace(temporary, target)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: merge-env.py TARGET_ENV UPDATES_ENV")
    merge(Path(sys.argv[1]), read_updates(Path(sys.argv[2])))
