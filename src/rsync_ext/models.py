from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rsync_ext.constants import DEFAULT_DESTINATION_PATH, DEFAULT_SSH_PORT


@dataclass(slots=True)
class Connection:
    id: str
    label: str
    host: str
    port: int = DEFAULT_SSH_PORT
    username: str = ""
    auth_type: str = "password"
    private_key_path: str | None = None
    default_destination_path: str = DEFAULT_DESTINATION_PATH
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "Connection":
        auth_type = str(data.get("auth_type", "password"))
        private_key_path = data.get("private_key_path")
        if private_key_path:
            private_key_path = str(Path(private_key_path).expanduser())

        return cls(
            id=str(data["id"]),
            label=str(data["label"]).strip(),
            host=str(data["host"]).strip(),
            port=int(data.get("port", DEFAULT_SSH_PORT)),
            username=str(data["username"]).strip(),
            auth_type=auth_type,
            private_key_path=private_key_path,
            default_destination_path=str(
                data.get("default_destination_path", DEFAULT_DESTINATION_PATH)
            ).strip()
            or DEFAULT_DESTINATION_PATH,
            enabled=bool(data.get("enabled", True)),
        )

    def to_dict(self) -> dict:
        data = {
            "id": self.id,
            "label": self.label,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "auth_type": self.auth_type,
            "default_destination_path": self.default_destination_path,
            "enabled": self.enabled,
        }
        if self.private_key_path:
            data["private_key_path"] = self.private_key_path
        return data

    def validate(self) -> None:
        if not self.id:
            raise ValueError("Connection id is required.")
        if not self.label:
            raise ValueError("Connection label is required.")
        if not self.host:
            raise ValueError("Host or IP address is required.")
        if not self.username:
            raise ValueError("Username is required.")
        if self.port <= 0 or self.port > 65535:
            raise ValueError("Port must be between 1 and 65535.")
        if self.auth_type not in {"password", "ssh_key"}:
            raise ValueError("Authentication type must be password or ssh_key.")
        if self.auth_type == "ssh_key" and not self.private_key_path:
            raise ValueError("A private key path is required for SSH key auth.")
        if self.auth_type == "ssh_key" and self.private_key_path:
            expanded = Path(self.private_key_path).expanduser()
            if not expanded.exists():
                raise ValueError("The selected private key file does not exist.")
            if _looks_like_public_key_file(expanded):
                raise ValueError(
                    "The selected SSH key looks like a public key. Choose the private key file instead."
                )
        if not self.default_destination_path:
            raise ValueError("Default destination path is required.")


def _looks_like_public_key_file(path: Path) -> bool:
    if path.suffix == ".pub":
        return True

    try:
        first_line = path.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip()
    except Exception:
        return False

    public_key_prefixes = (
        "ssh-ed25519 ",
        "ssh-rsa ",
        "ecdsa-sha2-",
        "sk-ecdsa-",
        "sk-ssh-ed25519",
        "-----BEGIN SSH2 PUBLIC KEY-----",
    )
    return first_line.startswith(public_key_prefixes)
