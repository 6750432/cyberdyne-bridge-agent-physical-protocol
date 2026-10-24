#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CBAP device contract v1.

Every driver registered with the Kernel is normalized into the same
descriptor shape.  The contract is about *rights and lifecycle*, not about
pretending that different hardware has the same capabilities.

Required fields are intentionally small enough for a test driver but strict
enough that a production driver cannot silently omit trust, isolation,
resource, or safety metadata.
"""
from __future__ import annotations

import copy
import os
import re
from typing import Any

CONTRACT = "cbap-device-v1"
DEVICE_CLASSES = {
    "actuator", "sensor", "display", "input", "filesystem", "composite", "test",
}
CAPABILITIES = {"read", "write", "lease", "estop", "admin"}
ATTESTATIONS = {"none", "local-hash", "remote", "hardware"}
SANDBOXES = {"none", "process", "uid", "bwrap", "nsjail", "portal"}
SAFE_STATES = {
    "off", "idle", "input-disabled", "read-only", "stopped", "unknown",
}
_ACTION_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_DEVICE_RE = re.compile(r"^[A-Za-z0-9_.-]+://[^\s]{1,240}$")


class ContractError(ValueError):
    pass


def _class_for(raw: dict) -> str:
    typ = str(raw.get("type") or "").lower()
    did = str(raw.get("device_id") or "")
    if did.startswith("host://input"):
        return "input"
    if did.startswith("host://display"):
        return "display"
    if did.startswith("host://fs") or did.startswith("host://desktop"):
        return "filesystem"
    if "minecraft" in typ or "mcp-device" in typ or "test-light" in typ:
        return "actuator"
    if "sensor" in typ:
        return "sensor"
    if "test" in typ:
        return "test"
    return "composite"


def _actions_for(raw: dict) -> dict[str, dict]:
    actions = raw.get("actions")
    if isinstance(actions, dict):
        out = {}
        for name, spec in actions.items():
            spec = spec if isinstance(spec, dict) else {}
            out[str(name)] = {
                "args": copy.deepcopy(spec.get("args") or {}),
                "result": copy.deepcopy(spec.get("result") or {}),
                "danger": str(spec.get("danger") or "normal"),
                "idempotent": bool(spec.get("idempotent", False)),
            }
        return out
    names: set[str] = set()
    if isinstance(actions, list):
        names.update(str(x) for x in actions)
    if isinstance(raw.get("tools"), list):
        names.update(str(x) for x in raw["tools"])
    if isinstance(raw.get("write"), list):
        names.update(str(x) for x in raw["write"])
    mapping = raw.get("mapping") or {}
    if isinstance(mapping, dict):
        names.update(str(x) for x in (mapping.get("ops") or {}).keys())
    return {name: {"args": {}, "result": {}, "danger": "normal",
                   "idempotent": False}
            for name in sorted(names) if _ACTION_RE.fullmatch(name)}


def _safety_for(raw: dict) -> dict:
    raw_safety = raw.get("safety") if isinstance(raw.get("safety"), dict) else {}
    estop = raw_safety.get("estop")
    if isinstance(estop, str):
        estop = bool(estop)
    if estop is None:
        estop = False
    try:
        watchdog = int(raw_safety.get("watchdog_ms") or 10000)
    except (TypeError, ValueError):
        watchdog = 10000
    safe_state = str(raw_safety.get("safe_state") or "unknown")
    return {
        "estop": bool(estop),
        "watchdog_ms": max(100, watchdog),
        "safe_state": safe_state if safe_state in SAFE_STATES else "unknown",
    }


def _resources_for(raw: dict) -> dict:
    limits = raw.get("limits") if isinstance(raw.get("limits"), dict) else {}
    resources = raw.get("resources") if isinstance(raw.get("resources"), dict) else {}

    def val(name, default, minimum=1):
        value = resources.get(name, limits.get(name, default))
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = default
        return max(minimum, value)

    return {
        "max_inflight": val("max_inflight", 4, 1),
        "rate_hz": val("rate_hz", 20, 1),
        "max_bytes": val("max_bytes", int(limits.get("max_frame", 65536)), 16),
        "max_sessions": val("max_sessions", 32, 1),
    }


def _trust_for(raw: dict) -> dict:
    facts = raw.get("facts") if isinstance(raw.get("facts"), dict) else {}
    trust = raw.get("trust") if isinstance(raw.get("trust"), dict) else {}
    independent = trust.get("independent", raw.get("facts_independent",
                                                   facts.get("independent", False)))
    source = str(trust.get("facts_source") or trust.get("source") or
                 facts.get("source") or raw.get("type") or "unknown")
    attestation = str(trust.get("attestation") or "none")
    if attestation not in ATTESTATIONS:
        attestation = "none"
    level = trust.get("level")
    if level is None:
        level = 2 if independent else 1
    try:
        level = max(0, min(3, int(level)))
    except (TypeError, ValueError):
        level = 1
    return {
        "source": source,
        "independent": bool(independent),
        "attestation": attestation,
        "level": level,
    }


def _isolation_for(raw: dict) -> dict:
    isolation = raw.get("isolation") if isinstance(raw.get("isolation"), dict) else {}
    sandbox = str(isolation.get("sandbox") or "none")
    if sandbox not in SANDBOXES:
        sandbox = "none"
    uid = isolation.get("uid")
    try:
        uid = int(uid) if uid is not None else os.getuid()
    except (TypeError, ValueError):
        uid = os.getuid()
    return {
        "process": str(isolation.get("process") or "in-process"),
        "uid": uid,
        "sandbox": sandbox,
        "network": str(isolation.get("network") or "local"),
    }


def normalize_contract(raw: dict, *, strict: bool = False) -> dict:
    """Return a validated copy of a driver descriptor with contract fields.

    ``strict=True`` rejects descriptors missing declared contract metadata.
    The Kernel uses strict mode for registered devices; legacy normalization is
    available to migration tools and old test fixtures.
    """
    if not isinstance(raw, dict):
        raise ContractError("descriptor must be an object")
    device_id = raw.get("device_id")
    if not isinstance(device_id, str) or not _DEVICE_RE.fullmatch(device_id):
        raise ContractError(f"invalid device_id: {device_id!r}")
    declared = raw.get("contract")
    if strict and declared != CONTRACT:
        raise ContractError(f"{device_id}: missing contract {CONTRACT}")
    out = copy.deepcopy(raw)
    out["contract"] = CONTRACT
    out["device_id"] = device_id
    out["version"] = str(raw.get("version") or "1.0")
    cls = raw.get("class", raw.get("device_class"))
    if cls is None:
        cls = _class_for(raw)
    if cls not in DEVICE_CLASSES:
        raise ContractError(f"{device_id}: invalid class {cls!r}")
    out["class"] = cls

    actions = _actions_for(raw)
    for name in actions:
        if not _ACTION_RE.fullmatch(name):
            raise ContractError(f"{device_id}: invalid action {name!r}")
    out["actions"] = actions

    caps = raw.get("capabilities")
    # Legacy MC descriptors use "capabilities" for domain abilities
    # (locomotion, vision, ...), not CBAP rights.  Only a declared contract may
    # assert CBAP rights; otherwise derive the default rights below.
    if (caps is not None and declared == CONTRACT and
            isinstance(caps, list) and caps):
        caps = [str(c) for c in caps]
        unknown = set(caps) - CAPABILITIES
        if unknown:
            raise ContractError(f"{device_id}: unknown capabilities {sorted(unknown)}")
    else:
        caps = ["read", "write", "lease", "estop"] if actions else ["read", "estop"]
    if not isinstance(caps, list) or not caps:
        raise ContractError(f"{device_id}: capabilities must be a non-empty list")
    out["capabilities"] = sorted(set(caps))

    out["trust"] = _trust_for(raw)
    out["isolation"] = _isolation_for(raw)
    out["resources"] = _resources_for(raw)
    out["safety"] = _safety_for(raw)
    if strict:
        for section in ("trust", "isolation", "resources", "safety"):
            if not isinstance(raw.get(section), dict):
                raise ContractError(f"{device_id}: missing {section} section")
    # A marker useful for migration audits.  Production drivers should be
    # declared (legacy=False); old test fixtures normalize to legacy=True.
    out["legacy"] = bool(raw.get("legacy", declared != CONTRACT))
    return out


def contract_summary(contract: dict) -> dict:
    """Small welcome/discovery projection; no secrets or raw schemas."""
    return {
        "device_id": contract["device_id"],
        "class": contract["class"],
        "version": contract["version"],
        "contract": contract["contract"],
        "actions": sorted(contract["actions"]),
        "capabilities": contract["capabilities"],
        "trust": contract["trust"],
        "isolation": contract["isolation"],
        "resources": contract["resources"],
        "safety": contract["safety"],
        "legacy": contract["legacy"],
    }
