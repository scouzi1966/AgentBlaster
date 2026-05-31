from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from agentblaster.errors import ConfigError
from agentblaster.models import ProviderConfig, ProvidersFile


def app_home() -> Path:
    override = os.environ.get("AGENTBLASTER_HOME")
    if override:
        return Path(override).expanduser()
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home).expanduser() / "agentblaster"
    return Path.home() / ".config" / "agentblaster"


def providers_path(home: Path | None = None) -> Path:
    return (home or app_home()) / "providers.json"


class ProviderStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or providers_path()

    def load(self) -> ProvidersFile:
        if not self.path.exists():
            return ProvidersFile()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return ProvidersFile.model_validate(data)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise ConfigError(f"invalid provider config at {self.path}: {exc}") from exc

    def save(self, providers_file: ProvidersFile) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = providers_file.model_dump(mode="json", exclude_none=True)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def upsert(self, provider: ProviderConfig) -> None:
        providers_file = self.load()
        providers_file.providers[provider.name] = provider
        self.save(providers_file)

    def get(self, name: str) -> ProviderConfig:
        providers_file = self.load()
        try:
            return providers_file.providers[name]
        except KeyError as exc:
            raise ConfigError(f"unknown provider: {name}") from exc

    def list(self) -> list[ProviderConfig]:
        return sorted(self.load().providers.values(), key=lambda provider: provider.name)
