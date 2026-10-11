"""Agent publisher: validate and atomically persist an immutable linked pair."""

from backend.app.forecasting.contracts import validate


class Publisher:
    def __init__(self, store):
        self.store = store

    def publish(self, specialist, coordinated):
        validate(specialist)
        validate(coordinated)
        if (
            specialist["role"] != "specialist"
            or coordinated["role"] != "coordinated"
            or specialist["id"] == coordinated["id"]
            or coordinated.get("specialist_forecast_id") != specialist["id"]
            or coordinated.get("weights") != {specialist["specialist_id"]: 1.0}
            or any(
                specialist[k] != coordinated[k]
                for k in (
                    "run_id",
                    "origin",
                    "model_version",
                    "dataset_version",
                    "points",
                    "probabilities",
                    "origin_price",
                )
            )
        ):
            raise ValueError("Invalid coordinated pass-through pair")
        return self.store.publish(specialist, coordinated)
