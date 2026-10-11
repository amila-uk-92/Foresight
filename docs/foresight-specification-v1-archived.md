# Foresight — Consolidated Implementation Prompt

You are implementing **Foresight**, a local cryptocurrency forecasting application.

Build a working system that downloads and displays historical Bitcoin data, trains a price-and-volume forecasting specialist, produces a seven-day forecast, saves the forecast, and evaluates it against actual outcomes.

The eventual architecture will support multiple specialists. **For this implementation, enable only the Bitcoin price-and-volume specialist.** Keep the coordinator, publisher and evaluator as separate components so additional specialists can be added later.

Read this entire specification before implementing.

## 1. Existing application and design references

The historical dataset explorer has been reported complete. Inspect the existing repository and verify its functionality before extending it.

Reuse working data services, storage, API contracts and approved design tokens. Correct missing requirements where necessary.

Reference inputs:

```text
Dataset Explorer reference:
[ATTACH IMAGE OR INSERT ACCESSIBLE URL]

Main Dashboard reference:
[ATTACH THE SELECTED DASHBOARD IMAGE OR INSERT ACCESSIBLE URL]

Specialist Inspect reference:
[ATTACH IMAGE OR INSERT ACCESSIBLE URL, IF AVAILABLE]
```

Several dashboard alternatives have been discussed. Implement the explicitly selected reference. Do not combine competing layouts or silently select one.

Treat the supplied reference as the visual specification. Match its layout, typography, colours, spacing, borders, icons and component proportions.

Approved factual corrections take precedence over illustrative content:

- Training duration is 36 months.
- Prices, counts, probabilities and metrics must come from actual data and model outputs.
- Statuses must reflect real processing states.
- Forecast dates must agree across the chart and summary.
- A median forecast must be labelled “Median,” not “Expected.”
- Concept and illustrative labels are removed only when genuine outputs are displayed.
- Baseline labels must describe the actual baseline being evaluated.

Do not embed a screenshot as the application. Implement the components and their interactions.

## 2. Current scope

Implement:

1. Historical Bitcoin data import and quality checks.
2. Dataset Explorer with chronological split visualisation.
3. One trained price-and-volume specialist.
4. Coordinator operating as a validated single-specialist pass-through.
5. Forecast publisher with immutable forecast history.
6. Evaluator with baseline comparisons.
7. Historical replay.
8. Controlled specialist retraining, candidate comparison, promotion and rollback.
9. Main forecast dashboard and specialist Inspect panel.

Do not implement:

- Derivatives, cross-market, on-chain, news or social specialists.
- Trading, order execution or portfolio management.
- Exchange-account authentication.
- Cloud deployment.
- Learned coordinator weights while only one specialist exists.

If Ethereum data already exists from the dataset phase, preserve it in the explorer. Do not use it as an input to the active forecasting specialist.

## 3. Technology and responsibilities

Use the existing stack where it already satisfies these requirements. The agreed stack is:

- Python for data processing, training, prediction and evaluation.
- FastAPI for backend endpoints.
- React, TypeScript and Vite for the frontend.
- TradingView Lightweight Charts for historical market visualisation, with suitable chart extensions or a compatible chart solution for forecast intervals.
- Parquet for processed market data.
- SQLite for local jobs, forecast records, model metadata and evaluation records.
- Local files for raw archives, model artifacts, manifests and reports.

Check current official dependency documentation during implementation and pin dependency versions.

Keep business logic outside API handlers and UI components. CLI commands and API endpoints must call the same underlying services.

Agents are independently testable components with defined responsibilities and versioned contracts. They do not all need language models.

The active specialist uses a numerical forecasting model. Validation, coordination, persistence and scoring use deterministic code.

## 4. End-to-end behaviour

The system operates as follows:

1. Import historical BTC/USDT hourly candles.
2. Verify their integrity and report missing or invalid data.
3. Assign observations to training, validation and final-test periods.
4. Build forecasting examples using only information available at each forecast origin.
5. Train candidate price-and-volume models.
6. Select settings and calibrate uncertainty using earlier chronological development data.
7. Freeze the selected configuration before final-test replay.
8. At each replay origin, generate seven daily forecast points and a weekly summary.
9. The coordinator validates the specialist output and passes it through unchanged.
10. The publisher saves both specialist and coordinated forecasts.
11. The dashboard displays the saved forecast.
12. As outcomes become available in replay time, the evaluator scores the forecast.
13. In adaptive mode, controlled retraining may use only outcomes that have already matured.
14. Save every model version, forecast and promotion decision for inspection.

A forecast must never be altered after seeing its actual outcome.

## 5. Historical dataset

Primary dataset:

```text
Market: Binance Spot
Symbol: BTCUSDT
Native interval: 1h
Timezone: UTC

Start inclusive: 2022-10-01 00:00:00 UTC
End exclusive:   2026-10-01 00:00:00 UTC
```

Keep these dates configurable, with the above values as the fixed default.

Use public Binance historical archives:

```text
https://data.binance.vision/data/spot/monthly/klines/{symbol}/1h/{symbol}-1h-{YYYY-MM}.zip
```

Consult the official public-data documentation:

```text
https://github.com/binance/binance-public-data
```

Public archive downloads require no account credentials.

Preserve raw archives and verify published SHA-256 checksums.

Support:

- Bounded concurrent downloads.
- Timeouts, bounded retries and backoff.
- Atomic writes.
- Cancellation and resume.
- Reuse of verified files.
- Progress and per-file failures.
- A source manifest recording URL, checksum, retrieval time and status.

Do not start downloading automatically when the app launches. Require an explicit import action.

### Parsing and quality checks

Preserve timestamps, OHLC prices, base and quote volumes, trade counts, taker-buy volumes and source-file identity.

Handle milliseconds in older Binance spot archives and microseconds in archives from January 2025. Normalize to UTC and verify resulting dates.

Validate:

- Schema and finite numeric values.
- Positive prices.
- Non-negative volumes and trade counts.
- Valid OHLC relationships.
- Hourly alignment and chronological ordering.
- Duplicate and conflicting records.
- Missing hours.
- Requested versus actual coverage.

Do not silently forward-fill or manufacture candles.

Distinguish BTC base volume from USDT quote volume.

Completed candle values become available only after their close. Preserve this availability rule throughout feature generation and replay.

Expected complete coverage is 35,064 hourly candles for the default BTC period. Display actual counts and any discrepancy.

## 6. Chronological periods

Use these half-open UTC intervals:

| Period | Start inclusive | End exclusive | Duration |
|---|---|---|---|
| Training | 2022-10-01 | 2025-10-01 | 36 months |
| Validation | 2025-10-01 | 2026-06-01 | 8 months |
| Final test | 2026-06-01 | 2026-10-01 | 4 months |

Expected complete hourly counts:

- Training: 26,304.
- Validation: 5,832.
- Final test: 2,928.

These are raw-observation counts, not counts of eligible forecasting examples.

Use chronological subdivisions of earlier development data for model selection, uncertainty calibration and candidate comparison.

Safeguards:

- Never randomly split time-series examples.
- Fit preprocessing only on the permitted fitting period.
- Training examples’ full future targets must remain inside their permitted period.
- Validation targets must not cross into final test.
- Historical look-back context may extend into an earlier period.
- Incomplete future targets remain unavailable.
- Final-test outcomes must not influence model selection or manual tuning.

If final-test results inform a subsequent design change, label that run as development. Do not continue presenting that same period as an untouched final test.

## 7. Forecast definition

Forecast BTC/USDT spot prices at seven horizons:

```text
+24h, +48h, +72h, +96h, +120h, +144h, +168h
```

At every horizon produce:

- Median price estimate.
- Lower bound for an 80% prediction interval.
- Upper bound for an 80% prediction interval.

For the seven-day summary produce:

- Day-seven median price.
- Return implied by that median relative to the origin price.
- Day-seven prediction interval.
- Probability of a positive seven-day return.
- Probability of a negative seven-day return.

Document how exactly zero returns are handled so probabilities remain coherent.

Use one precise target-price convention. For example, at a UTC forecast origin, use the close of the last completed hourly candle as the origin price; use the corresponding completed-candle close at each future horizon as the target.

Apply this convention consistently in training, prediction, charts and evaluation.

The weekly summary must use the same day-seven output displayed on the chart.

The forecast contains seven daily points. Do not invent an intraday forecast path.

Label the uncertainty band as **pointwise 80% prediction intervals**. It does not represent an 80% guarantee that the entire seven-day path stays within the band.

## 8. Price-and-volume specialist

The specialist receives Bitcoin price and volume history available at the origin.

Inputs may include derived features such as:

- Lagged returns.
- Rolling volatility.
- Rolling trends.
- Recent high-low ranges.
- Volume changes.
- Base or quote volume measures.
- Calendar features.

Exclude Ethereum, derivatives, news, social data and future observations.

Separate these concepts in code and UI:

- **Training history:** historical examples used to fit the model.
- **Look-back window:** observations used to create inputs for one prediction.
- **Forecast horizon:** seven days into the future.

Do not describe a 90-day look-back as the model’s entire training history.

Evaluate configurable look-back candidates such as 30, 90 and 180 days using development data. These are candidates, not assumed optimal values.

Begin with manageable model families such as regularized regression or gradient-boosted trees. Select using the agreed chronological protocol.

Prefer direct horizon-specific return forecasts. Convert returns to prices using the origin price.

Implement genuine uncertainty estimation and chronological calibration. Prevent quantile crossing.

Generate rise/fall probabilities using a documented probabilistic model or predictive distribution. Do not create arbitrary confidence percentages from a price estimate.

Training must save:

- Model artifact and version.
- Configuration.
- Feature definitions.
- Training cutoff.
- Dataset version.
- Selection and calibration periods.
- Development metrics.

## 9. Forecast contract

Each specialist forecast must contain:

- Forecast ID and run ID.
- Specialist ID.
- Contract and model versions.
- Symbol, market and quote currency.
- Forecast origin.
- Actual generation timestamp.
- Latest input availability timestamp.
- Dataset version.
- Training cutoff.
- Origin price.
- Seven target timestamps and horizon lengths.
- Median forecasts and interval bounds.
- Weekly direction probabilities.
- Central-estimate and interval definitions.
- Configuration identity.
- Quality flags and status.

Validate positive finite prices, ordered intervals, valid probabilities, correct horizons and provenance.

No input availability timestamp may exceed the forecast origin.

Distinguish historical simulated time from actual wall-clock execution time.

## 10. Coordinator

With one specialist enabled, the coordinator:

1. Receives its forecast.
2. Validates the contract and data freshness.
3. Rejects invalid or unavailable output.
4. Passes valid predictions through unchanged.
5. Records specialist weight `1.0`.
6. Creates a distinct coordinated forecast linked to the specialist forecast.

Display:

```text
Single-specialist pass-through
```

Do not suggest that the coordinator is learning weights in this phase.

Use a specialist registry and contracts that can later support multiple specialists. Future additions must not require rewriting forecast storage or evaluation.

## 11. Publisher and persistence

The publisher saves forecasts before the UI displays them or the evaluator scores them.

Persist:

- Original specialist output.
- Coordinated output.
- Provenance and weights.
- Model and data versions.
- Configuration.
- Origin and generation timestamps.
- Processing status and quality flags.

Forecast predictions are immutable.

Store evaluation records separately and attach actual outcomes without modifying predictions.

Allow users to retrieve and inspect any earlier forecast.

Make jobs and persistence idempotent. Restarting or retrying must not create unintended duplicate forecasts.

## 12. Evaluator

Evaluate specialist and coordinated forecasts separately, even though their predictions initially match.

For each horizon calculate:

- Absolute price error.
- Absolute return error, with units stated.
- Interval coverage.
- Interval width.
- A proper interval score.

For day seven also calculate:

- Direction accuracy.
- Brier score for the positive-return probability.
- Probability calibration summaries when enough samples exist.

Compare against:

- No-change price forecast.
- Historical-frequency direction forecast.
- A documented baseline uncertainty model.

Estimate baseline parameters from earlier available data only.

Show metrics by horizon, model version and replay mode. Include sample counts.

Account for overlapping seven-day windows when reporting statistical uncertainty.

Evaluation states:

```text
Pending
Partially evaluated
Fully evaluated
Unscorable due to missing data
```

Do not substitute a neighbouring candle when the exact target is missing.

An evaluator measures outcomes. It does not retrain a model by itself.

## 13. Historical replay and learning

Provide two separately labelled modes.

### Frozen-model replay

- Select and freeze the model before final test.
- Step through test origins chronologically.
- Generate forecasts using only information available at each origin.
- Score outcomes only when available to the replay clock.
- Keep the model fixed throughout the run.

### Adaptive replay

- Start from a model established before final test.
- Use a predeclared retraining schedule and promotion policy.
- Permit training only on examples whose targets have matured by the simulated cutoff.
- Maintain the same no-future-information rules.
- Keep adaptive results separate from frozen results.

Default forecast cadence: once daily at a documented UTC time.

At the end of the available dataset, horizons without outcomes remain pending or unscorable as appropriate. Do not invent later actuals.

### Controlled retraining

Implement:

1. Candidate training.
2. Comparison with incumbent and baselines on identical earlier held-out cases.
3. Checks of point error and uncertainty quality.
4. Promotion only when predeclared criteria pass.
5. Retention of the incumbent otherwise.
6. Recorded evidence and decision.
7. Rollback to an earlier model version.

Report insufficient evidence honestly.

Coordinator learning remains inactive until multiple specialists exist.

## 14. Main dashboard

Use the selected main-dashboard reference and the application’s shared visual language.

The dashboard must show:

- BTC/USDT and UTC.
- Selected model and forecast origin.
- Two distinct actions.
- Four agent components.
- Historical price and forecast chart.
- Weekly forecast summary.
- Historical replay controls.
- Evaluation summary.

**Do not include the removed Experiment Stages panel or a stages stepper.**

### Train & Backtest action

This starts a background workflow that:

1. Verifies dataset readiness.
2. Builds eligible examples.
3. Trains candidates using permitted training data.
4. Performs model selection and uncertainty calibration using development data.
5. Saves the selected model.
6. Runs the configured frozen or adaptive replay.
7. Persists forecasts and scores.
8. Updates the dashboard with actual results.

Expose essential configuration in a compact modal or settings drawer: date periods, replay mode, model configuration and retraining policy where applicable.

Do not make final-test metrics part of automatic model selection.

Show progress through real agent statuses and a compact job status area. Provide cancellation and meaningful errors without adding the removed stages panel.

### Predict Next 7 Days action

This uses an already trained selected model.

It:

1. Checks required history and data quality.
2. Uses the latest eligible completed candle, or an explicitly selected historical origin.
3. Generates the specialist forecast.
4. Passes it through the coordinator.
5. Saves it through the publisher.
6. Displays its seven daily points and weekly summary.

It does not silently retrain or run an entire backtest.

If no model exists, explain that training is required and provide access to Train & Backtest.

If the dataset ends in the past, label the prediction with its historical origin. Do not call it a current live forecast.

## 15. Agent cards and Inspect behaviour

Show four components:

| Component | Responsibility | Example truthful states |
|---|---|---|
| Price & Volume | Train and forecast | Not trained, Training, Ready, Predicting, Failed |
| Coordinator | Validate and pass through | Waiting, Validating, Complete, Rejected |
| Publisher | Save forecasts | Waiting, Saving, Saved, Failed |
| Evaluator | Score available outcomes | Pending, Evaluating, Partial, Complete, Unscorable |

Statuses must correspond to the selected run or forecast. Avoid presenting unrelated jobs as one coherent pipeline.

The Price & Volume **Inspect** button opens a side drawer or panel. It does not start training.

Show:

- Specialist purpose and permitted inputs.
- Model version and family.
- Training-history dates.
- Training cutoff.
- Look-back window.
- Dataset version.
- Latest input availability.
- Feature definitions and relevant input summary.
- Seven daily forecast values and intervals.
- Weekly probabilities.
- Quality flags.
- Evaluation results where available.

Keep inputs, forecast outputs and later actual outcomes clearly distinguishable.

Provide a close action and preserve the dashboard’s chart selection when the panel closes.

## 16. Forecast chart and weekly summary

The main chart displays:

- Historical BTC price before the origin.
- A labelled forecast-origin divider.
- Seven daily predicted points.
- Pointwise uncertainty shading.
- Actual outcomes as a separate optional overlay.
- Clear legend and USDT price axis.

Support:

- Pan and zoom.
- Crosshair tooltips.
- Selection of a forecast point.
- Historical range selection.
- Forecast and actual visibility toggles.
- Forecast-history selection.

Tooltips show timestamp, horizon, median, interval and actual price when available.

Chart dates, summary dates and stored target timestamps must match exactly.

The weekly summary displays:

- Origin price and time.
- Day-seven target time.
- Median price.
- Implied return.
- Lower and upper interval bounds.
- Rise/fall probabilities.
- Model version.
- Evaluation state.

Changing the selected forecast updates all these components together.

## 17. Replay controls and evaluation UI

Replay controls provide:

- Run selection.
- Frozen/adaptive label.
- Origin-date selection.
- Play/pause.
- Step forward/backward.
- Replay speed.
- Progress through historical origins.

Playing replay advances the simulated display and reveals saved forecasts and outcomes according to replay time. It must not retrain merely because the user presses Play.

Distinguish replay navigation from launching a new backend run.

The evaluation summary shows actual computed metrics and sample counts. Use “—” with an explanatory pending state when metrics are unavailable.

Provide an Evaluation view with:

- Metrics by horizon.
- Baseline comparisons.
- Coverage and interval width.
- Direction and probability metrics.
- Scorable/unscorable counts.
- Model-version filters.
- Separate frozen/adaptive results.

Provide Forecast History with origin, model, run, weekly estimate, evaluation status and an Inspect action.

## 18. Dataset Explorer UI

Preserve the approved dataset page.

Include:

- Symbol, interval, date-range and timezone controls.
- Training, validation and final-test cards.
- Cyan training, amber validation and violet test identification where specified by the reference.
- Real historical candles and volume.
- Split shading and timestamp-aligned boundaries.
- Dataset metadata and quality results.
- Candle inspector.
- Import progress, cancellation and errors.

Selecting a split focuses the chart and table on that period. Allow resetting to full history.

Display actual counts, percentages and volume units.

Keep chart direction colours distinct from split colours. Expose gaps rather than concealing them.

## 19. UI states and responsiveness

Design coherent states for:

- No dataset.
- Importing or incomplete import.
- Quality warnings.
- No trained model.
- Training.
- Replay running.
- Prediction running.
- Forecast ready.
- Awaiting actual outcomes.
- Partial evaluation.
- Failed or cancelled jobs.
- API unavailable.

Never display fictitious learning activity or invented performance.

Disable conflicting actions and explain why. Preserve user selections through refresh where practical.

Desktop must closely match the selected reference. On mobile, rearrange panels while preserving readable charts, controls and text. Use horizontal table scrolling where needed.

## 20. API and job interfaces

Provide endpoints for:

- Dataset inventory, metadata and quality.
- Range-filtered candles and paginated inspection rows.
- CSV export.
- Import creation, status and cancellation.
- Training/backtest job creation, status and cancellation.
- Model inventory, metadata and rollback.
- Forecast creation and retrieval.
- Forecast history.
- Replay runs and their saved origins.
- Evaluation results and summaries.
- Agent status for a selected run or forecast.

Use background jobs for imports, training and replay.

Persist job state, prevent conflicting operations and recover truthfully after restart. Do not leave abandoned jobs permanently marked Running.

## 21. Verification and acceptance

Test meaningful cases covering:

- Timestamp-unit normalization.
- Checksums, gaps and conflicting duplicates.
- Exact chronological boundaries.
- Features excluding future information.
- Full target-window eligibility.
- Outcome availability during replay.
- Contract validation.
- Coordinator pass-through equality.
- Immutable forecast persistence.
- Idempotent retries.
- Missing actuals.
- Hand-calculated evaluation metrics.
- Valid probabilities and ordered intervals.
- Candidate promotion and rollback.
- Agreement between chart, summary and stored forecasts.

Run a complete historical replay and report measured results, including failure to beat baselines.

Verify visual fidelity using screenshots at the reference viewport, side-by-side comparisons and overlays. Exclude changing data pixels from strict comparisons while checking chart geometry and styling.

Deliver:

- Complete source code and dependency files.
- Reusable Python CLI.
- Setup and local-run instructions.
- Data manifests and quality reports.
- Versioned model artifacts and configurations.
- Saved example forecasts.
- Replay and evaluation reports.
- Relevant tests.
- Desktop/mobile screenshots and reference comparisons.
- Known limitations.

The system is complete when a user can import genuine historical Bitcoin data, inspect the chronological periods, train the price-and-volume specialist, run historical evaluation, generate and inspect a seven-day forecast, and see truthful results through the coordinator, publisher and evaluator.

The architecture must permit future specialists, but only price and volume is active now. Predictive value must be established by evaluation; it is not assumed as an acceptance condition.