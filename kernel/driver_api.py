#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stable driver interface and agent-manifest discovery for CBAP.

This module is deliberately independent from the current drivers.  It defines
what an agent sub-repository must expose to become a CBAP peripheral, without
changing any runtime path yet.

Contract:

    Agent subrepo
      agent.json
      adapter / driver package
        factory(**config) -> DeviceDriver

The CBAP main repository owns this interface, the kernel, leases, safety, and
the conformance suite.  It does not own the agent's implementation.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

SCHEMA = "cbap-agent/1"


@runtime_checkable
class DeviceDriver(Protocol):
    """The minimum device-facing contract used by the legacy Kernel.

    This is intentionally small: it describes the boundary the current
    `KernelServer` already relies on.  New capabilities (cancel, restart,
    subscriptions, ...) should be added as optional extensions, not by
    weakening this contract.
    """

    def describe(self) -> dict[str, Any]:
        ...

    def health(self) -> dict[str, Any]:
        ...

    def send(self, command: dict[str, Any]) -> bool:
        ...

    def estop(self) -> bool:
        ...

    def close(self) -> None:
        ...


DriverFactory = Callable[..., DeviceDriver]


@dataclass(frozen=True)
class AgentManifest:
    """Parsed `agent.json` for one agent sub-repository."""

    path: Path
    raw: dict[str, Any]

    @property
    def id(self) -> str:
        return str(self.raw.get("id") or self.path.parent.name)

    @property
    def display_name(self) -> str:
        return str(self.raw.get("display_name") or self.id)

    @property
    def status(self) -> str:
        return str(self.raw.get("status") or "unknown")

    @property
    def kind(self) -> str:
        return str(self.raw.get("kind") or "unknown")

    @property
    def cbap(self) -> dict[str, Any]:
        value = self.raw.get("cbap") or {}
        return value if isinstance(value, dict) else {}

    @property
    def active(self) -> bool:
        return self.status == "active"

    @property
    def loadable(self) -> bool:
        return bool(self.cbap.get("driver_module")
                    and self.cbap.get("driver_factory"))

    @classmethod
    def read(cls, path: Path) -> "AgentManifest":
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError(f"agent manifest is not an object: {path}")
        if raw.get("schema") != SCHEMA:
            raise ValueError(
                f"unsupported manifest schema in {path}: {raw.get('schema')!r}")
        return cls(path=path, raw=raw)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.id:
            errors.append("id is required")
        if not self.status:
            errors.append("status is required")
        cbap = self.cbap
        if cbap and not self.loadable and not cbap.get("adapter"):
            errors.append("cbap needs driver_module + driver_factory or adapter")
        return errors

    def resolve_factory(self) -> DriverFactory:
        """Import and return the declared Python driver factory.

        Importing happens only on explicit load, never during discovery.
        Node/HTTP adapters are handled by their own subrepo and are not
        importable through this function.
        """
        module_name = str(self.cbap.get("driver_module") or "")
        factory_name = str(self.cbap.get("driver_factory") or "")
        if not module_name or not factory_name:
            raise ValueError(f"{self.id}: no Python driver factory declared")
        module = importlib.import_module(module_name)
        factory = getattr(module, factory_name)
        if not callable(factory):
            raise TypeError(f"{self.id}: {module_name}.{factory_name} is not callable")
        return factory


class DriverRegistry:
    """Discover agent sub-repositories from a directory of manifests."""

    def __init__(self, root: Path | str | None = None):
        if root is None:
            root = Path(__file__).resolve().parents[1] / "agents"
        self.root = Path(root)

    def discover(self) -> dict[str, AgentManifest]:
        found: dict[str, AgentManifest] = {}
        if not self.root.is_dir():
            return found
        for path in sorted(self.root.glob("*/agent.json")):
            manifest = AgentManifest.read(path)
            errors = manifest.validate()
            if errors:
                raise ValueError(f"{path}: " + "; ".join(errors))
            if manifest.id in found:
                raise ValueError(f"duplicate agent id: {manifest.id}")
            found[manifest.id] = manifest
        return found

    def active(self) -> dict[str, AgentManifest]:
        return {k: v for k, v in self.discover().items() if v.active}

    def get(self, agent_id: str) -> AgentManifest:
        return self.discover()[agent_id]
