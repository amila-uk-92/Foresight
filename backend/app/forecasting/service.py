"""Shared application/CLI workflow; scientific work stays outside HTTP handlers."""

import uuid
import hashlib
import inspect
import json
from contextlib import contextmanager
import numpy as np
from backend.app.config import SPLITS, REPORTS_DIR
from backend.app.markets import get_market, primary_market
from backend.app.storage import Store, now, atomic_json
from backend.app.jobs import jobs
from backend.app.forecasting.data import MarketData
from backend.app.forecasting import data as data_module
from backend.app.forecasting import specialist as specialist_module
from backend.app.forecasting.features import get_feature_set
from backend.app.forecasting.specialist import (
    train,
    predict,
    loss,
    stamp,
    iso,
    uses_final_test_outcomes,
    model_market,
)
from backend.app.forecasting.contracts import coordinate
from backend.app.forecasting.publisher import Publisher
from backend.app.forecasting.evaluator import (
    evaluate,
    aggregate,
    interval_score,
    AGENT_EVALUATION_STATES,
)

PROMOTION_POLICY = {
    "cadence_days": 30,
    "comparison_days": 45,
    "minimum_daily_origins": 30,
    "mae_improvement_fraction": 0.01,
    "interval_score_must_not_worsen": True,
    "coverage_floor": 0.7,
    "baseline_mae_must_not_worsen": True,
}


HISTORY_DAYS = (7, 30, 90, 180, 365)


def legacy_protocol(lookbacks, alphas, features):
    # Fingerprint used before 10 Oct 2026; kept only to migrate stored settings.
    return hashlib.sha256(
        json.dumps(
            {
                "lookbacks": list(lookbacks),
                "alphas": list(alphas),
                "features": features,
                "periods": {
                    k: (v["start"].isoformat(), v["end"].isoformat())
                    for k, v in SPLITS.items()
                },
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


def protocol_fingerprint(lookbacks, alphas, market=None):
    """Everything that can change a frozen final-test result.

    Configuration alone is not enough: changing feature code, the model family,
    selection, calibration, the market calendar or the promotion policy after
    seeing final-test results must also mark later runs as development.
    """
    market = market or primary_market()
    feature_set = get_feature_set(market.feature_set)
    calendar = type(market.calendar)
    code = [
        inspect.getsource(data_module.MarketData.features),
        inspect.getsource(data_module.MarketData.examples),
        inspect.getsource(data_module.MarketData.input),
        inspect.getsource(specialist_module.fit),
        inspect.getsource(specialist_module.raw),
        inspect.getsource(specialist_module.distribution),
        inspect.getsource(specialist_module.loss),
        inspect.getsource(specialist_module.train),
        inspect.getsource(specialist_module.predict),
        inspect.getsource(feature_set.compute),
        inspect.getsource(calendar.is_origin),
        inspect.getsource(calendar.origins),
        inspect.getsource(calendar.horizon_target),
        inspect.getsource(calendar.horizon_hours),
    ]
    payload = {
        "lookbacks": list(lookbacks),
        "alphas": list(alphas),
        "features": feature_set.names,
        "periods": {
            k: (v["start"].isoformat(), v["end"].isoformat())
            for k, v in market.splits.items()
        },
        "promotion_policy": PROMOTION_POLICY,
        "code": hashlib.sha256("\n".join(code).encode()).hexdigest(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class AgentError(ValueError):
    def __init__(self, agent, message):
        super().__init__(message)
        self.agent = agent


class Engine:
    def __init__(self, store=None, job_runner=None, market=None):
        self.store = store or Store()
        # Agent cards read job state from the same durable store as the forecasts.
        self.jobs = job_runner or jobs
        # One engine per market. The primary market keeps the original setting keys.
        self.market = get_market(market) if market else primary_market()

    def _setting_key(self, name):
        if self.market.is_primary:
            return name
        return f"{name}:{self.market.symbol}"

    def setting(self, name, value=None):
        return self.store.setting(self._setting_key(name), value)

    def _own_runs(self):
        return [
            r
            for r in self.store.list("runs")
            if r.get("symbol", primary_market().symbol) == self.market.symbol
        ]

    def _own_models(self):
        return [
            m
            for m in self.store.list("models")
            if model_market(m).symbol == self.market.symbol and not m.get("news_experiment")
        ]

    @contextmanager
    def replacing_previous_run(self, job_id=None):
        """Keep one trained run per market: the new run replaces the old one only once it finishes.

        The body sets outcome["run_id"]. If it fails or is cancelled, everything it
        created is removed and the previous run stays exactly as it was.
        """
        before_runs = {r["id"] for r in self._own_runs()}
        before_models = {m["id"] for m in self._own_models()}
        outcome = {}
        try:
            yield outcome
        except BaseException:
            self.keep_only(before_runs, before_models)
            raise
        self.keep_only({outcome["run_id"]}, job_id=job_id, select=True)

    def keep_only(self, run_ids, model_ids=None, job_id=None, select=False):
        """Remove this market's other runs, models, forecasts, scores and records.

        Without model_ids, the kept models are the ones the kept runs use. With job_id,
        older finished forecasting jobs go too; with select, the kept run's model is selected.
        """
        runs = self._own_runs()
        kept = [r for r in runs if r["id"] in run_ids]
        if model_ids is None:
            model_ids = set()
            for r in kept:
                model_ids |= {r.get("model_id"), r.get("initial_model_id")}
                model_ids |= {m["model_id"] for m in r.get("models", [])}
                model_ids |= {
                    f["model_version"] for f in self.store.list("forecasts", r["id"])
                }
            model_ids.discard(None)
            model_ids.discard("")
        drop_runs = {r["id"] for r in runs if r["id"] not in run_ids}
        drop_models = {m["id"] for m in self._own_models() if m["id"] not in model_ids}
        drop_decisions = [
            d["id"]
            for d in self.store.list("decisions")
            if d.get("run_id") in drop_runs
            or d.get("incumbent") in drop_models
            or d.get("candidate") in drop_models
        ]
        self.store.remove(
            drop_runs,
            drop_models,
            drop_decisions,
            jobs_kind="forecasting" if job_id else None,
            keep_job=job_id,
            symbol=self.market.symbol,
        )
        # Saved model files and run reports leave with their rows. When this store is
        # the data folder's own database, stray model files no stored model uses go too.
        models_dir = specialist_module.DATA_DIR / "models"
        stray = set(drop_models)
        if self.store.path.parent.resolve() == specialist_module.DATA_DIR.resolve():
            known = {m["id"] for m in self.store.list("models")}
            stray |= {p.stem for p in models_dir.glob("pv-*.json") if p.stem not in known}
        for id in stray:
            (models_dir / f"{id}.json").unlink(missing_ok=True)
        for run_id in drop_runs:
            for path in REPORTS_DIR.glob(f"{run_id}_*.json"):
                path.unlink(missing_ok=True)
        selected = self.setting("selected_model")
        if select and kept and selected not in model_ids:
            self.setting(
                "selected_model", kept[0].get("initial_model_id") or kept[0]["model_id"]
            )
        elif selected and selected in drop_models:
            self.setting("selected_model", "")
        if drop_runs or drop_models:
            self.store.compact()

    def load_data(self, version=None):
        return MarketData.load(version, symbol=self.market.symbol)

    def publish(self, data, model, origin, run_id, mode):
        # Each agent's failure is attributed to that agent, never to "the pipeline".
        try:
            specialist = predict(data, model, origin, run_id, mode)
        except ValueError as e:
            raise AgentError("specialist", str(e)) from e
        try:
            coordinated = coordinate(specialist)
        except ValueError as e:
            raise AgentError("coordinator", str(e)) from e
        try:
            return Publisher(self.store).publish(specialist, coordinated)
        except ValueError as e:
            raise AgentError("publisher", str(e)) from e

    def score(self, data, f, clock):
        existing = self.store.evaluation(f["id"])
        if existing and (
            existing["scored_count"] == 7 or stamp(existing["clock"]) >= clock
        ):
            return
        self.store.evaluation(f["id"], evaluate(data, f, clock))
        original = self.store.get("forecasts", f["specialist_forecast_id"])
        self.store.evaluation(original["id"], evaluate(data, original, clock))

    def candidate(self, data, incumbent, clock, run_id, check, progress):
        # Candidate selection/calibration end BEFORE the independent comparison window.
        cutoff = clock - PROMOTION_POLICY["comparison_days"] * 86400
        candidate = train(
            data,
            self.store,
            check,
            progress,
            cutoff=cutoff,
            lookbacks=(incumbent["configuration"]["lookback_days"],),
            alphas=(incumbent["configuration"]["alpha"],),
        )
        cases = data.examples(
            incumbent["configuration"]["lookback_days"], cutoff, clock
        )
        n = len(cases[0])
        if n < 30:
            decision = {
                "promoted": False,
                "reason": "Insufficient independent earlier evidence",
                "sample_count": n,
            }
        else:
            old, new = loss(incumbent, cases), loss(candidate, cases)
            actual = cases[3][:, None] * np.exp(cases[2])
            baseline_mae = float(np.mean(np.abs(actual - cases[3][:, None])))
            earlier = data.examples(
                incumbent["configuration"]["lookback_days"],
                cutoff - 180 * 86400,
                cutoff,
            )
            if len(earlier[0]) < 30:
                decision = {
                    "promoted": False,
                    "reason": "Insufficient baseline evidence",
                    "sample_count": n,
                }
            else:
                q = np.quantile(earlier[2], [0.1, 0.9], axis=0)
                lower = cases[3][:, None] * np.exp(q[0])
                upper = cases[3][:, None] * np.exp(q[1])
                baseline_score = float(
                    np.mean(
                        (upper - lower)
                        + 10 * np.maximum(lower - actual, 0)
                        + 10 * np.maximum(actual - upper, 0)
                    )
                )
                promoted = (
                    new["mae_usdt"] <= old["mae_usdt"] * 0.99
                    and new["mae_usdt"] <= baseline_mae
                    and new["interval_score_usdt"]
                    <= min(old["interval_score_usdt"], baseline_score)
                    and new["coverage"] >= 0.7
                )
                decision = dict(
                    promoted=promoted,
                    reason=(
                        "Predeclared criteria passed"
                        if promoted
                        else "Retain incumbent: criteria not met"
                    ),
                    sample_count=n,
                    incumbent_metrics=old,
                    candidate_metrics=new,
                    baseline_mae_usdt=baseline_mae,
                    baseline_interval_score_usdt=baseline_score,
                )
        decision.update(
            id=uuid.uuid4().hex,
            created_at=now(),
            run_id=run_id,
            clock=iso(clock),
            incumbent=incumbent["id"],
            candidate=candidate["id"],
            comparison_start=iso(cutoff),
            comparison_end=iso(clock),
            policy=PROMOTION_POLICY,
            uses_final_test_outcomes=clock
            > self.market.splits["validation"]["end"].timestamp(),
        )
        self.store.put("decisions", decision, immutable=True)
        return candidate if decision["promoted"] else incumbent

    def train_backtest(self, config=None, job_id=None):
        with self.replacing_previous_run(job_id) as outcome:
            result = self._train_backtest(config, job_id)
            outcome["run_id"] = result["run_id"]
        return result

    def _train_backtest(self, config=None, job_id=None):
        config = config or {}
        mode = config.get("mode", "frozen")
        if mode not in ("frozen", "adaptive"):
            raise ValueError("Choose frozen or adaptive replay")
        lookbacks = tuple(config.get("lookbacks", [30, 90, 180]))
        alphas = tuple(config.get("alphas", [1.0, 10.0, 100.0]))
        if (
            not lookbacks
            or any(d not in (30, 90, 180) for d in lookbacks)
            or not alphas
            or any(a <= 0 or not np.isfinite(a) for a in alphas)
        ):
            raise ValueError("Invalid model configuration")
        check = lambda: jobs.check(job_id) if job_id else None

        def progress(label, pct, agents=None):
            check()
            if job_id:
                jobs.update(
                    job_id,
                    current_step=label,
                    progress_percentage=pct,
                    agents=agents
                    or {
                        "specialist": "Training",
                        "coordinator": "Waiting",
                        "publisher": "Waiting",
                        "evaluator": "Pending",
                    },
                )

        progress(f"Verifying {self.market.base_asset} dataset integrity", 2)
        data = self.load_data()
        check()
        model = train(
            data, self.store, check, progress, lookbacks=lookbacks, alphas=alphas
        )
        initial = model
        protocol = protocol_fingerprint(lookbacks, alphas, self.market)
        development, reason = self.protocol_status(
            protocol, legacy_protocol(lookbacks, alphas, model["features"])
        )
        run = dict(
            id=uuid.uuid4().hex,
            created_at=now(),
            mode=mode,
            status="running",
            symbol=self.market.symbol,
            model_id=model["id"],
            initial_model_id=model["id"],
            dataset_version=data.version,
            config=config,
            promotion_policy=PROMOTION_POLICY,
            start=iso(self.market.splits["final_test"]["start"].timestamp()),
            end=iso(self.market.splits["final_test"]["end"].timestamp()),
            cadence="daily 00:00 UTC",
            clock=iso(self.market.splits["final_test"]["start"].timestamp()),
            skipped_origins=[],
            development=development,
            development_reason=reason,
            protocol_id=protocol,
            uses_final_test_outcomes=mode == "adaptive",
            evaluation_label=(
                "Development: " + reason
                if development
                else (
                    "Adaptive final-test replay: retraining uses only matured "
                    "final-test outcomes; reported separately from frozen"
                    if mode == "adaptive"
                    else "Final test: configuration selected only from earlier development data"
                )
            ),
        )
        self.store.put("runs", run)
        if job_id:
            jobs.update(job_id, run_id=run["id"])
        start, end = stamp(run["start"]), stamp(run["end"])
        origins = data.calendar.origins(start, end)
        published = []
        try:
            for j, origin in enumerate(origins):
                check()
                if (
                    mode == "adaptive"
                    and j > 0
                    and j % PROMOTION_POLICY["cadence_days"] == 0
                ):
                    progress(
                        "Training earlier-data candidate", 45 + 50 * j / len(origins)
                    )
                    model = self.candidate(
                        data,
                        model,
                        origin,
                        run["id"],
                        check,
                        lambda label, p: progress(label, 45 + 50 * j / len(origins)),
                    )
                progress(
                    f"Replay {iso(origin)[:10]}",
                    45 + 50 * j / len(origins),
                    {
                        "specialist": "Predicting",
                        "coordinator": "Validating",
                        "publisher": "Saving",
                        "evaluator": "Evaluating",
                    },
                )
                try:
                    f = self.publish(data, model, origin, run["id"], mode)
                    published.append(f)
                except ValueError as e:
                    run["skipped_origins"].append(
                        {
                            "origin": iso(origin),
                            "agent": getattr(e, "agent", "specialist"),
                            "reason": str(e),
                        }
                    )
                # Score ONLY after replay clock reaches exact target maturity.
                for f in published:
                    self.score(data, f, origin)
                run.update(clock=iso(origin), model_id=model["id"])
                self.store.put("runs", run)
            check()
            if not published:
                raise ValueError(
                    "No eligible test origins. See skipped-origin reasons."
                )
            for f in published:
                self.score(data, f, end)
            run.update(status="complete", clock=iso(end), model_id=model["id"])
            run["summary"] = aggregate(self.store, run["id"])
            self.store.put("runs", run)
            atomic_json(REPORTS_DIR / f'{run["id"]}_replay.json', run)
            # Explicit training selects pre-test model; adaptive end model remains run-specific.
            self.setting("selected_model", initial["id"])
            if job_id:
                jobs.update(
                    job_id,
                    agents={
                        "specialist": "Ready",
                        "coordinator": "Complete",
                        "publisher": "Saved",
                        "evaluator": (
                            "Partial"
                            if any(
                                self.store.evaluation(f["id"])["scored_count"] < 7
                                for f in published
                            )
                            else "Complete"
                        ),
                    },
                )
            return {
                "run_id": run["id"],
                "model_id": initial["id"],
                "forecast_id": published[-1]["id"] if published else None,
            }
        except BaseException:
            run.update(status="interrupted", summary=aggregate(self.store, run["id"]))
            self.store.put("runs", run)
            raise

    def train_and_predict(self, config=None, job_id=None, origin=None):
        """One user action: train, replay the final test, then predict from the selected model."""
        with self.replacing_previous_run(job_id) as outcome:
            result = self._train_and_predict(config, job_id, origin)
            outcome["run_id"] = result["replay_run_id"]
        return result

    def _train_and_predict(self, config=None, job_id=None, origin=None):
        replay = self._train_backtest(config, job_id)
        check = lambda: jobs.check(job_id) if job_id else None
        if job_id:
            jobs.update(
                job_id,
                current_step="Predicting next 7 days",
                progress_percentage=97,
                agents={
                    "specialist": "Predicting",
                    "coordinator": "Validating",
                    "publisher": "Saving",
                    "evaluator": "Pending",
                },
            )
        f = self.predict(origin, replay["model_id"], check)
        if job_id:
            jobs.update(
                job_id,
                agents={
                    "specialist": "Ready",
                    "coordinator": "Complete",
                    "publisher": "Saved",
                    "evaluator": "Pending",
                },
            )
        # forecast_id is the new prediction; the replay stays reachable by its run.
        return {
            "forecast_id": f["id"],
            "model_id": replay["model_id"],
            "replay_run_id": replay["run_id"],
            "replay_forecast_id": replay["forecast_id"],
        }

    def predict(self, origin=None, model_id=None, check=lambda: None):
        model_id = model_id or self.setting("selected_model")
        if not model_id:
            raise ValueError("No selected trained model. Use Train & Predict first.")
        model = self.store.get("models", model_id)
        data = MarketData.load(model["dataset_version"], model_market(model).symbol)
        t = stamp(origin) if origin else int(data.times[-1])
        # Stable standalone run identity ensures retry idempotency.
        run_id = "prediction-" + model_id
        check()
        f = self.publish(data, model, t, run_id, "prediction")
        self.score(data, f, t)
        return f

    def retrain(self, model_id, cutoff, job_id=None):
        model = self.store.get("models", model_id)
        data = MarketData.load(model["dataset_version"], model_market(model).symbol)
        clock = stamp(cutoff)
        if clock > data.times[-1] or clock <= stamp(model["training_cutoff"]):
            raise ValueError(
                "Retraining cutoff must be later than model cutoff and within observed data"
            )
        check = lambda: jobs.check(job_id) if job_id else None
        updated = self.candidate(
            data,
            model,
            clock,
            "manual-retraining",
            check,
            lambda label, p: (
                jobs.update(job_id, current_step=label, progress_percentage=p)
                if job_id
                else None
            ),
        )
        check()
        self.setting("selected_model", updated["id"])
        return {"model_id": updated["id"], "promoted": updated["id"] != model_id}

    def rollback(self, model_id):
        model = self.store.get("models", model_id)
        selected = self.setting("selected_model")
        decision = dict(
            id=uuid.uuid4().hex,
            created_at=now(),
            kind="rollback",
            incumbent=selected,
            candidate=model_id,
            promoted=True,
            reason="Explicit user model selection; no predictions changed",
        )
        self.store.put("decisions", decision, immutable=True)
        self.setting("selected_model", model_id)
        return model

    def detail(self, id, history_days=30):
        f = self.store.get("forecasts", id)
        data = MarketData.load(f["dataset_version"], f["symbol"])
        origin = stamp(f["origin"])
        visible_clock = origin
        if f["mode"] in ("frozen", "adaptive"):
            visible_clock = stamp(self.store.get("runs", f["run_id"])["clock"])
        else:
            ev = self.store.evaluation(id)
            if ev:
                visible_clock = stamp(ev["clock"])
        if history_days not in HISTORY_DAYS:
            raise ValueError(f"History range must be one of {HISTORY_DAYS} days")
        # Hourly for a week; every 6 hours to 90 days; daily beyond. Origin always kept.
        step = 3600 if history_days <= 7 else (21600 if history_days <= 90 else 86400)
        history = [
            {"time": int(t), "close": float(p)}
            for t, p in zip(data.times, data.close)
            if origin - history_days * 86400 <= t <= origin
            and (int(t) % step == 0 or t == origin)
        ]
        ev = self.store.evaluation(id)
        actuals = [
            {"time": int(stamp(p["target"])), "close": p["actual_price"]}
            for p in (ev or {}).get("points", [])
            if p["state"] == "evaluated" and stamp(p["target"]) <= visible_clock
        ]
        return dict(
            forecast=f,
            evaluation=ev,
            model=self.store.get("models", f["model_version"]),
            history=history,
            history_days=history_days,
            history_step_seconds=step,
            actuals=actuals,
            visible_clock=iso(visible_clock),
            agents=self.agent_status(forecast_id=id),
        )

    def protocol_status(self, protocol, legacy):
        """Return (development, reason) for a new replay under this protocol."""
        frozen = self.setting("frozen_protocol_v2")
        if frozen is None:
            earlier = self.setting("frozen_protocol")
            if earlier is not None and earlier != legacy:
                return True, (
                    "configuration differs from the protocol first reported on the final test"
                )
            # First run under the stricter fingerprint. Earlier reports used the same
            # configuration, so this code becomes the reference protocol.
            self.setting("frozen_protocol_v2", protocol)
            return False, None
        if frozen != protocol:
            return True, (
                "configuration, model code or promotion policy changed after "
                "final-test results were reported"
            )
        return False, None

    def evaluate_at(self, forecast_id, clock):
        """Score one saved forecast at an explicit clock (shared by API and CLI)."""
        f = self.store.get("forecasts", forecast_id)
        data = MarketData.load(f["dataset_version"], f["symbol"])
        t = stamp(clock)
        if t > data.times[-1] or t < stamp(f["origin"]):
            raise ValueError(
                "Evaluation clock must be within observed data and not before the origin"
            )
        self.score(data, f, t)
        return self.store.evaluation(forecast_id)

    def models(self):
        selected = self.setting("selected_model")
        return [
            {
                **{k: v for k, v in m.items() if k not in ("parameters", "residuals")},
                "selected": m["id"] == selected,
                "uses_final_test_outcomes": uses_final_test_outcomes(m),
            }
            for m in self.store.list("models")
            if model_market(m).symbol == self.market.symbol and not m.get("news_experiment")
        ]

    def runs(self):
        return [
            {k: v for k, v in r.items() if k != "summary"}
            for r in self.store.list("runs")
            if r.get("symbol", primary_market().symbol) == self.market.symbol
        ]

    def run_origins(self, run_id):
        run = self.store.get("runs", run_id)
        saved = sorted(
            (
                {
                    "origin": f["origin"],
                    "forecast_id": f["id"],
                    "model_version": f["model_version"],
                    "evaluation_state": (self.store.evaluation(f["id"]) or {}).get(
                        "state", "pending"
                    ),
                }
                for f in self.store.list("forecasts", run_id)
            ),
            key=lambda r: r["origin"],
        )
        return dict(
            run_id=run_id,
            mode=run["mode"],
            clock=run["clock"],
            saved=saved,
            skipped=run.get("skipped_origins", []),
        )

    def run_scores(self, run_id, model_id=None):
        """Per-origin, per-horizon outcomes for one run, as stored (never recomputed)."""
        self.store.get("runs", run_id)
        rows = []
        for f in sorted(self.store.list("forecasts", run_id), key=lambda f: f["origin"]):
            if model_id and f["model_version"] != model_id:
                continue
            ev = {p["horizon_hours"]: p for p in (self.store.evaluation(f["id"]) or {}).get("points", [])}
            points = []
            for p in f["points"]:
                e = ev.get(p["horizon_hours"], {})
                scored = e.get("state") == "evaluated"
                points.append(
                    dict(
                        state=e.get("state", "pending"),
                        median=p["median"],
                        lower=p["lower"],
                        upper=p["upper"],
                        actual=e.get("actual_price") if scored else None,
                        covered=e.get("interval_coverage") if scored else None,
                        error=e.get("absolute_price_error") if scored else None,
                        # The no-change baseline predicts the origin close for every horizon.
                        baseline_error=abs(e["actual_price"] - f["origin_price"]) if scored else None,
                    )
                )
            rows.append(
                dict(
                    forecast_id=f["id"],
                    origin=f["origin"],
                    model_version=f["model_version"],
                    origin_price=f["origin_price"],
                    positive_probability=f["probabilities"]["positive"],
                    points=points,
                )
            )
        return dict(run_id=run_id, rows=rows)

    def history(self, page=1, page_size=50, run_id=None, mode=None, model_id=None):
        rows = [
            f
            for f in self.store.list("forecasts")
            if f["role"] == "coordinated"
            and f["symbol"] == self.market.symbol
            and (run_id is None or f["run_id"] == run_id)
            and (mode is None or f["mode"] == mode)
            and (model_id is None or f["model_version"] == model_id)
        ]
        items = []
        for f in rows[(page - 1) * page_size : page * page_size]:
            day7 = f["points"][6]
            ev = self.store.evaluation(f["id"]) or {}
            outcome = next(
                (p for p in ev.get("points", []) if p["horizon_hours"] == 168 and p.get("state") == "evaluated"),
                None,
            )
            items.append(
                dict(
                    id=f["id"],
                    origin=f["origin"],
                    generated_at=f["generated_at"],
                    run_id=f["run_id"],
                    mode=f["mode"],
                    model_version=f["model_version"],
                    origin_price=f["origin_price"],
                    day7_target=day7["target"],
                    day7_median=day7["median"],
                    day7_lower=day7["lower"],
                    day7_upper=day7["upper"],
                    implied_return=day7["median"] / f["origin_price"] - 1,
                    positive_probability=f["probabilities"]["positive"],
                    evaluation_state=ev.get("state", "pending"),
                    scored_count=ev.get("scored_count", 0),
                    day7_actual=outcome["actual_price"] if outcome else None,
                    day7_error=outcome["absolute_price_error"] if outcome else None,
                    quality_flags=f["quality_flags"],
                )
            )
        return dict(total=len(rows), page=page, page_size=page_size, rows=items)

    def agent_status(self, forecast_id=None, run_id=None):
        """Truthful per-agent state for one forecast (or one run when no forecast).

        A running job only drives the cards when it belongs to the same run;
        unrelated jobs are never presented as this forecast's pipeline.
        """
        f = self.store.get("forecasts", forecast_id) if forecast_id else None
        run_id = f["run_id"] if f else run_id
        run = None
        if run_id and not run_id.startswith("prediction-"):
            try:
                run = self.store.get("runs", run_id)
            except ValueError:
                run = None
        job = self.jobs.get(kind="forecasting")
        same_job = bool(
            job
            and job["status"] not in ("complete", "failed", "cancelled")
            and (job.get("run_id") == run_id or (not f and not run_id))
        )
        if same_job:
            return dict(
                source="active_job",
                job_id=job["job_id"],
                specialist=job["agents"].get("specialist", "Waiting"),
                coordinator=job["agents"].get("coordinator", "Waiting"),
                publisher=job["agents"].get("publisher", "Waiting"),
                evaluator=job["agents"].get("evaluator", "Pending"),
                details={},
            )
        skipped = (run or {}).get("skipped_origins", [])
        rejected = [x for x in skipped if x.get("agent") == "coordinator"]
        failed = [x for x in skipped if x.get("agent", "specialist") == "specialist"]
        unsaved = [x for x in skipped if x.get("agent") == "publisher"]
        details = {
            "specialist_failed_origins": len(failed),
            "coordinator_rejected_origins": len(rejected),
            "publisher_failed_origins": len(unsaved),
        }
        if f:
            model = self.store.get("models", f["model_version"])
            ev = self.store.evaluation(f["id"])
            return dict(
                source="forecast",
                forecast_id=f["id"],
                specialist="Ready",
                coordinator="Complete",
                publisher="Saved",
                evaluator=AGENT_EVALUATION_STATES[(ev or {}).get("state", "pending")],
                model_version=model["id"],
                details=details,
            )
        if run:
            last_job = next(
                (
                    j
                    for j in self._jobs_for_run(run["id"])
                    if j["status"] in ("failed", "cancelled")
                ),
                None,
            )
            interrupted = run["status"] == "interrupted"
            return dict(
                source="run",
                run_id=run["id"],
                specialist=(
                    "Failed"
                    if interrupted and last_job and last_job["status"] == "failed"
                    else ("Cancelled" if interrupted else "Ready")
                ),
                coordinator="Rejected" if rejected else "Complete",
                publisher="Failed" if unsaved else "Saved",
                evaluator="Pending",
                details=details,
            )
        selected = self.setting("selected_model")
        return dict(
            source="none",
            specialist="Ready" if selected else "Not trained",
            coordinator="Waiting",
            publisher="Waiting",
            evaluator="Pending",
            details={},
        )

    def _jobs_for_run(self, run_id):
        with self.jobs.store.connection() as db:
            rows = db.execute(
                "SELECT payload FROM jobs WHERE kind='forecasting' ORDER BY created DESC"
            ).fetchall()
        return [j for j in (json.loads(r["payload"]) for r in rows) if j.get("run_id") == run_id]
