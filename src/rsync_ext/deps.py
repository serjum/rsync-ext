from __future__ import annotations

import shutil
from dataclasses import dataclass


@dataclass(slots=True)
class DependencyStatus:
    name: str
    available: bool
    path: str | None
    required_for: str


def check_dependencies(include_sshpass: bool = True) -> list[DependencyStatus]:
    required = [
        ("rsync", "all transfers"),
        ("ssh", "all transfers"),
    ]
    if include_sshpass:
        required.append(("sshpass", "password-based connections"))

    result = []
    for name, required_for in required:
        path = shutil.which(name)
        result.append(
            DependencyStatus(
                name=name,
                available=path is not None,
                path=path,
                required_for=required_for,
            )
        )
    return result


def ensure_binary(name: str, reason: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"Missing required dependency '{name}' for {reason}.")
    return path

