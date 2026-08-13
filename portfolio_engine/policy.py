from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


def _try_load_yaml(path: Path) -> dict[str, Any]:
    if yaml is not None:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data if isinstance(data, dict) else {}

    # Fallback for minimal YAML subset without external dependency.
    data: dict[str, Any] = {}
    current_key: str | None = None
    current_map: dict[str, Any] | None = None

    with path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.rstrip()
            if not line or line.lstrip().startswith("#"):
                continue
            if line.startswith("  "):
                if ":" not in line:
                    continue
                key, _, value = line.strip().partition(":")
                key = key.strip()
                value = value.strip()
                if current_map is not None:
                    current_map[key] = value.strip('"') if value else None
                elif current_key is not None:
                    data.setdefault(current_key, {})[key] = value.strip('"') if value else None
            else:
                key, _, _ = line.partition(":")
                current_key = key.strip()
                data[current_key] = {}
                current_map = data[current_key]

    return data


def load_policy(policy_dir: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    base_dir = Path(policy_dir) if policy_dir is not None else Path(__file__).resolve().parent.parent / "portfolio_policy"
    files = [
        "risk_limits.yaml",
        "tax_profile.yaml",
        "tax_rules.yaml",
        "leverage_rules.yaml",
        "rebalance_rules.yaml",
        "execution_rules.yaml",
    ]

    merged: dict[str, Any] = {}
    for name in files:
        path = Path(base_dir) / name
        if not path.exists():
            continue
        loaded = _try_load_yaml(path)
        if isinstance(loaded, dict):
            for key, value in loaded.items():
                if key not in merged:
                    merged[key] = value
                elif isinstance(merged[key], dict) and isinstance(value, dict):
                    merged[key].update(value)
                else:
                    merged[key] = value
    return merged
