"""Versioned agent contract and deterministic single-specialist coordinator."""

import copy
import math
import uuid
from datetime import datetime, timedelta, timezone
from backend.app.markets import get_market

# Specialist registry: which markets each specialist may publish forecasts for.
# A new market is enabled for a specialist with register_specialist_market().
REGISTRY = {"price-volume": {"symbol": "BTCUSDT", "contract_version": "1.0"}}
SPECIALIST_MARKETS = {"price-volume": {"BTCUSDT"}}


def register_specialist_market(specialist_id, symbol, contract_version="1.0"):
    REGISTRY.setdefault(
        specialist_id, {"symbol": symbol, "contract_version": contract_version}
    )
    SPECIALIST_MARKETS.setdefault(specialist_id, set()).add(symbol)


def unregister_specialist_market(specialist_id, symbol):
    SPECIALIST_MARKETS.get(specialist_id, set()).discard(symbol)


def validate(f):
    required = (
        "id",
        "run_id",
        "specialist_id",
        "contract_version",
        "model_version",
        "symbol",
        "market",
        "quote_currency",
        "origin",
        "generated_at",
        "latest_input_availability",
        "dataset_version",
        "training_cutoff",
        "configuration_id",
        "origin_price",
        "points",
        "probabilities",
        "definitions",
        "quality_flags",
        "status",
    )
    if not isinstance(f, dict) or any(k not in f for k in required):
        raise ValueError("Incomplete forecast provenance")
    if (
        f["specialist_id"] not in REGISTRY
        or f["symbol"] not in SPECIALIST_MARKETS.get(f["specialist_id"], ())
        or f["contract_version"] != REGISTRY[f["specialist_id"]]["contract_version"]
    ):
        raise ValueError("Unsupported specialist contract")
    market = get_market(f["symbol"])
    if (
        f["status"] != "ready"
        or f["market"] != market.venue
        or f["quote_currency"] != market.quote_asset
    ):
        raise ValueError("Unavailable forecast or unsupported market")
    calendar = market.calendar
    if any(
        not isinstance(f[k], str) or not f[k]
        for k in (
            "id",
            "run_id",
            "model_version",
            "dataset_version",
            "configuration_id",
        )
    ):
        raise ValueError("Invalid provenance identity")
    origin = datetime.fromisoformat(f["origin"])
    if origin.tzinfo is None or origin.minute or origin.second or origin.microsecond:
        raise ValueError("Origin must be an exact UTC hour")
    if origin.utcoffset() != timedelta(0):
        raise ValueError("UTC required")
    availability = datetime.fromisoformat(f["latest_input_availability"])
    if availability != origin or datetime.fromisoformat(f["training_cutoff"]) > origin:
        raise ValueError("Future or stale provenance")
    if (
        not math.isfinite(f["origin_price"])
        or f["origin_price"] <= 0
        or len(f["points"]) != market.horizon_days
    ):
        raise ValueError("Invalid price/horizons")
    for day, p in enumerate(f["points"], 1):
        expected = datetime.fromtimestamp(
            calendar.horizon_target(origin.timestamp(), day), timezone.utc
        )
        if (
            p["horizon_hours"] != calendar.horizon_hours(day)
            or datetime.fromisoformat(p["target"]) != expected
        ):
            raise ValueError("Incorrect target")
        vals = [p["lower"], p["median"], p["upper"]]
        if not all(math.isfinite(x) and x > 0 for x in vals) or vals != sorted(vals):
            raise ValueError("Invalid interval")
    probabilities = [f["probabilities"][k] for k in ("positive", "negative", "zero")]
    if (
        not all(math.isfinite(x) and 0 <= x <= 1 for x in probabilities)
        or abs(sum(probabilities) - 1) > 1e-9
    ):
        raise ValueError("Invalid direction probabilities")
    if not f["dataset_version"] or not f["configuration_id"]:
        raise ValueError("Missing version")
    return f


def coordinate(specialist):
    validate(specialist)
    output = copy.deepcopy(specialist)
    output.update(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, specialist["id"] + ":coordinator:1.0")),
        role="coordinated",
        specialist_forecast_id=specialist["id"],
        coordinator_version="1.0",
        weights={specialist["specialist_id"]: 1.0},
        coordination="Single-specialist pass-through",
    )
    validate(output)
    return output
