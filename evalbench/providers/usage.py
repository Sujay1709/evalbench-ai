"""Allowlisted usage snapshots; absent measurements remain unknown."""

import math


def usage_snapshot(metadata: dict) -> dict:
    if not isinstance(metadata, dict):
        metadata = {}
    snapshot = {}
    for key in ("input_tokens", "output_tokens"):
        value = metadata.get(key)
        snapshot[key] = value if type(value) is int and value >= 0 else None
    cost = metadata.get("estimated_cost_usd")
    snapshot["estimated_cost_usd"] = (
        cost if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0 else None
    )
    # Pricing is an explicit estimate, never a claim about the provider's invoice.
    snapshot["cost_basis"] = (
        metadata.get("cost_basis") if isinstance(metadata.get("cost_basis"), str) else None
    )
    return snapshot
