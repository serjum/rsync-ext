#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = ROOT / "pyproject.toml"
PACKAGE_INIT_PATH = ROOT / "src" / "rsync_ext" / "__init__.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bump project version.")
    parser.add_argument(
        "part",
        choices=["patch", "minor", "major"],
        help="Which semantic version part to increment.",
    )
    return parser.parse_args()


def read_version() -> str:
    content = PYPROJECT_PATH.read_text(encoding="utf-8")
    match = re.search(r'^version = "(\d+)\.(\d+)\.(\d+)"$', content, re.MULTILINE)
    if not match:
        raise SystemExit("Could not find version in pyproject.toml")
    return ".".join(match.groups())


def bump_version(version: str, part: str) -> str:
    major, minor, patch = (int(piece) for piece in version.split("."))
    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1
    return f"{major}.{minor}.{patch}"


def replace_version(path: Path, pattern: str, new_version: str) -> None:
    content = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, rf'\g<1>{new_version}\g<2>', content, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"Could not update version in {path}")
    path.write_text(updated, encoding="utf-8")


def main() -> int:
    args = parse_args()
    current = read_version()
    new_version = bump_version(current, args.part)

    replace_version(PYPROJECT_PATH, r'^(version = ")\d+\.\d+\.\d+(")$', new_version)
    replace_version(PACKAGE_INIT_PATH, r'^(__version__ = ")\d+\.\d+\.\d+(")$', new_version)

    print(new_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
