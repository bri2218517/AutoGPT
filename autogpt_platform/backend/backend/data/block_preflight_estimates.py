"""Loader for the historical-average preflight cost estimates.

The JSON file is a snapshot of average credits-per-execution per block_id,
populated by an admin pulling fresh aggregates from `/admin/blocks/cost-estimates`
and committing the result. Used by `block_usage_cost()` to give dynamic-cost
blocks (SECOND/ITEMS/COST_USD) a non-zero pre-flight charge so post-flight
reconciliation only settles a small delta — bounding the billing-leak surface.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)

_ESTIMATES_PATH = Path(__file__).parent / "block_preflight_estimates.json"


class BlockPreflightEstimate(TypedDict):
    block_name: str
    cost_type: str
    samples: int
    mean_credits: int


_cache: dict[str, BlockPreflightEstimate] | None = None


def _load() -> dict[str, BlockPreflightEstimate]:
    global _cache
    if _cache is not None:
        return _cache
    try:
        raw = json.loads(_ESTIMATES_PATH.read_text())
        loaded: dict[str, BlockPreflightEstimate] = raw.get("estimates", {}) or {}
    except (FileNotFoundError, json.JSONDecodeError):
        logger.exception(
            "Failed to load %s; preflight estimates disabled", _ESTIMATES_PATH
        )
        loaded = {}
    _cache = loaded
    return loaded


def get_preflight_estimate(block_id: str) -> int:
    """Return the historical-average preflight cost for a block in credits.

    Returns 0 when no estimate is available (unseen block, low sample count,
    or file missing) so the caller falls back to the existing 0-preflight
    behaviour.
    """
    entry = _load().get(block_id)
    if not entry:
        return 0
    return int(entry.get("mean_credits", 0))


def reset_cache() -> None:
    """Test-only: drop the in-memory cache so a freshly-written JSON re-loads."""
    global _cache
    _cache = None
